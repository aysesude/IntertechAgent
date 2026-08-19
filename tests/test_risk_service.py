import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.config import AssetClass, RiskLevel, RiskProfile
from app.core.exceptions import NotFoundError
from app.models import Asset, Holding, Portfolio, PriceHistory, Transaction, TransactionType, User
from app.services.risk_service import get_risk_assessment


def _make_user_and_portfolio(db_session, risk_profile=RiskProfile.CONSERVATIVE):
    user = User(email="risk@example.com", full_name="Risk Test", risk_profile=risk_profile)
    db_session.add(user)
    db_session.flush()
    portfolio = Portfolio(user_id=user.id)
    db_session.add(portfolio)
    db_session.flush()
    return user, portfolio


def test_get_risk_assessment_raises_not_found_for_unknown_user(db_session):
    with pytest.raises(NotFoundError):
        get_risk_assessment(db_session, uuid.uuid4())


def test_get_risk_assessment_empty_portfolio_returns_neutral_result(db_session):
    user, _portfolio = _make_user_and_portfolio(db_session)
    db_session.commit()

    assessment = get_risk_assessment(db_session, user.id)

    assert assessment.risk_score is None
    assert assessment.risk_level is None
    assert assessment.total_value == Decimal(0)
    assert assessment.warnings  # bos portfoy uyarisi var
    assert assessment.metrics.correlation_matrix == []


def test_get_risk_assessment_insufficient_history_skips_stats_but_scores(db_session):
    """AK 2.7: az sayida ortak fiyat gunu varsa volatilite/korelasyon/VaR/Sharpe
    None doner, uyari eklenir, ama skor kalan olcutlerle (yogunlasma,
    cesitlendirme, varlik sinifi riski) hesaplanmaya devam eder."""
    user, portfolio = _make_user_and_portfolio(db_session)
    stock = Asset(symbol="TST", name="Test Hisse", asset_class=AssetClass.STOCK, currency="TRY")
    db_session.add(stock)
    db_session.flush()

    db_session.add_all(
        [
            PriceHistory(asset_id=stock.id, price_date=date(2026, 1, 1), close_price=Decimal(10)),
            PriceHistory(asset_id=stock.id, price_date=date(2026, 1, 2), close_price=Decimal(11)),
            Holding(
                portfolio_id=portfolio.id,
                asset_id=stock.id,
                quantity=Decimal(10),
                avg_cost_price=Decimal(10),
            ),
        ]
    )
    db_session.commit()

    assessment = get_risk_assessment(db_session, user.id)

    assert assessment.metrics.annualized_volatility_percent is None
    assert assessment.metrics.covariance_volatility_percent is None
    assert assessment.metrics.value_at_risk_try is None
    assert assessment.metrics.sharpe_ratio is None
    assert assessment.metrics.correlation_matrix == []
    assert any("en az" in w for w in assessment.warnings)
    # yetersiz veriye ragmen skor uydurulmadan, kalan olcutlerle hesaplanir
    assert assessment.risk_score is not None
    assert assessment.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH)


def test_get_risk_assessment_full_scenario_computes_stats_and_rebalance(db_session):
    """Yeterli ortak fiyat gunu (>= risk_min_price_points) olan iki varlikli
    bir portfoy: volatilite/korelasyon/VaR/Sharpe hesaplanmali, yogunlasma
    ve varlik sinifi riski tam olarak dogrulanabilmeli."""
    user, portfolio = _make_user_and_portfolio(db_session, risk_profile=RiskProfile.CONSERVATIVE)
    stock = Asset(symbol="TST", name="Test Hisse", asset_class=AssetClass.STOCK, currency="TRY")
    gold = Asset(
        symbol="TAU", name="Test Altin", asset_class=AssetClass.PRECIOUS_METAL, currency="TRY"
    )
    db_session.add_all([stock, gold])
    db_session.flush()

    start = date(2026, 1, 1)
    rows = []
    for i in range(40):
        day = start + timedelta(days=i)
        # basit ama sabit olmayan (deterministik) fiyat hareketleri
        stock_price = Decimal(100 + (i % 5) - 2)
        gold_price = Decimal(50 - (i % 3) + 1)
        rows.append(PriceHistory(asset_id=stock.id, price_date=day, close_price=stock_price))
        rows.append(PriceHistory(asset_id=gold.id, price_date=day, close_price=gold_price))
    db_session.add_all(rows)

    # esit agirlik: son gun (i=39) stock=100+(39%5)-2=102, gold=50-(39%3)+1=51
    # -> stock 10 adet=1020, gold 20 adet=1020, toplam=2040 (yine %50/%50)
    db_session.add_all(
        [
            Holding(
                portfolio_id=portfolio.id,
                asset_id=stock.id,
                quantity=Decimal(10),
                avg_cost_price=Decimal(95),
            ),
            Holding(
                portfolio_id=portfolio.id,
                asset_id=gold.id,
                quantity=Decimal(20),
                avg_cost_price=Decimal(45),
            ),
        ]
    )
    db_session.commit()

    assessment = get_risk_assessment(db_session, user.id)
    metrics = assessment.metrics

    assert assessment.total_value == Decimal("2040.00")
    assert metrics.price_points_used == 40
    assert metrics.holdings_count == 2

    # esit agirlik: max_asset_weight %50, HHI 0.5^2+0.5^2=0.5, etkin varlik 2
    assert metrics.max_asset_weight_percent == Decimal("50.00")
    assert metrics.herfindahl_index == Decimal("0.5000")
    assert metrics.effective_holdings_count == Decimal("2.00")

    # varlik sinifi bazli risk: 0.5*85 (hisse) + 0.5*50 (kiymetli maden) = 67.5
    assert metrics.asset_class_base_risk_score == Decimal("67.50")

    # yeterli veriyle istatistikler hesaplanmis olmali (None degil)
    assert metrics.annualized_volatility_percent is not None
    assert metrics.covariance_volatility_percent is not None
    assert metrics.value_at_risk_try is not None
    assert metrics.value_at_risk_try > 0
    assert metrics.value_at_risk_percent is not None
    assert metrics.value_at_risk_confidence == Decimal("95.00")
    assert metrics.sharpe_ratio is not None
    assert len(metrics.correlation_matrix) == 1  # tek cift: stock-gold
    pair = metrics.correlation_matrix[0]
    assert Decimal(-1) <= pair.correlation <= Decimal(1)
    assert not any("en az" in w for w in assessment.warnings)

    assert assessment.risk_score is not None
    assert assessment.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH)

    # yeniden dengeleme: conservative hedefte hisse %15, mevcut %50 -> SELL
    actions_by_class = {a.asset_class: a for a in assessment.rebalance_actions}
    assert actions_by_class[AssetClass.STOCK].action.value == "sell"
    assert actions_by_class[AssetClass.STOCK].current_percent == Decimal("50.00")
    assert not assessment.is_balanced


def test_get_risk_assessment_profile_override_does_not_persist(db_session):
    user, portfolio = _make_user_and_portfolio(db_session, risk_profile=RiskProfile.CONSERVATIVE)
    stock = Asset(symbol="TST", name="Test Hisse", asset_class=AssetClass.STOCK, currency="TRY")
    db_session.add(stock)
    db_session.flush()
    db_session.add_all(
        [
            PriceHistory(asset_id=stock.id, price_date=date(2026, 1, 1), close_price=Decimal(10)),
            Holding(
                portfolio_id=portfolio.id,
                asset_id=stock.id,
                quantity=Decimal(10),
                avg_cost_price=Decimal(10),
            ),
        ]
    )
    db_session.commit()

    assessment = get_risk_assessment(db_session, user.id, profile_override=RiskProfile.AGGRESSIVE)

    assert assessment.risk_profile == RiskProfile.AGGRESSIVE
    assert assessment.risk_profile_source.value == "override"
    db_session.refresh(user)
    assert user.risk_profile == RiskProfile.CONSERVATIVE  # DB'deki kalici profil degismedi


def test_get_risk_assessment_includes_cash_in_total_and_rebalance(db_session):
    """Nakit (defterden) toplam degere ve CASH dilimine dahil edilmeli,
    aksi halde yeniden dengeleme onerisi nakdi hic gormez."""
    user, portfolio = _make_user_and_portfolio(db_session)
    stock = Asset(symbol="TST", name="Test Hisse", asset_class=AssetClass.STOCK, currency="TRY")
    db_session.add(stock)
    db_session.flush()
    db_session.add(
        PriceHistory(asset_id=stock.id, price_date=date(2026, 1, 1), close_price=Decimal(10))
    )
    db_session.add(
        Holding(
            portfolio_id=portfolio.id,
            asset_id=stock.id,
            quantity=Decimal(10),
            avg_cost_price=Decimal(10),
        )
    )
    db_session.add(
        Transaction(
            portfolio_id=portfolio.id,
            transaction_type=TransactionType.DEPOSIT,
            transaction_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            cash_amount_try=Decimal(500),
        )
    )
    db_session.commit()

    assessment = get_risk_assessment(db_session, user.id)

    # hisse 10*10=100 + nakit 500 = 600
    assert assessment.total_value == Decimal("600.00")
    actions_by_class = {a.asset_class: a for a in assessment.rebalance_actions}
    assert actions_by_class[AssetClass.CASH].current_percent > Decimal(0)
