import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.config import AssetClass, RiskLevel, RiskProfile, settings
from app.core.exceptions import NotFoundError
from app.models import Asset, Holding, Portfolio, PriceHistory, Transaction, TransactionType, User
from app.services.risk_service import _risk_level_from_volatility, get_risk_assessment


def _make_user_and_portfolio(db_session, risk_profile=RiskProfile.CONSERVATIVE):
    user = User(email="risk@example.com", full_name="Risk Test", risk_profile=risk_profile)
    db_session.add(user)
    db_session.flush()
    portfolio = Portfolio(user_id=user.id)
    db_session.add(portfolio)
    db_session.flush()
    return user, portfolio


def test_risk_level_from_volatility_boundaries():
    """7 kademeli eşiklerin üst sınır dahil (<=) davrandığını doğrular
    (RISK_LEVEL_VOLATILITY_UPPER_BOUNDS, app/core/config.py)."""
    assert _risk_level_from_volatility(0.05) == RiskLevel.VERY_LOW
    assert _risk_level_from_volatility(0.051) == RiskLevel.LOW
    assert _risk_level_from_volatility(0.10) == RiskLevel.LOW
    assert _risk_level_from_volatility(0.101) == RiskLevel.LOW_MEDIUM
    assert _risk_level_from_volatility(0.15) == RiskLevel.LOW_MEDIUM
    assert _risk_level_from_volatility(0.20) == RiskLevel.MEDIUM
    assert _risk_level_from_volatility(0.30) == RiskLevel.MEDIUM_HIGH
    assert _risk_level_from_volatility(0.40) == RiskLevel.HIGH
    assert _risk_level_from_volatility(0.41) == RiskLevel.VERY_HIGH


def test_get_risk_assessment_raises_not_found_for_unknown_user(db_session):
    with pytest.raises(NotFoundError):
        get_risk_assessment(db_session, uuid.uuid4())


def test_get_risk_assessment_empty_portfolio_returns_neutral_result(db_session):
    user, _portfolio = _make_user_and_portfolio(db_session)
    db_session.commit()

    assessment = get_risk_assessment(db_session, user.id)

    assert assessment.risk_level is None
    assert assessment.is_within_profile is None
    assert assessment.total_value == Decimal(0)
    assert assessment.warnings  # bos portfoy uyarisi var
    assert assessment.metrics.category_metrics == []
    assert assessment.metrics.asset_metrics == []
    assert assessment.metrics.category_correlation_matrix == []
    assert assessment.causes is None
    assert assessment.scenarios == []


def test_get_risk_assessment_insufficient_history_skips_stats(db_session):
    """AK 2.7: az sayida ortak fiyat gunu varsa (risk_min_price_points'in
    altinda) volatilite/korelasyon/VaR/Sharpe VE risk seviyesi None doner,
    uyari eklenir — v2'de artik eski kompozit skorun dustugu bir "kalan
    olcutlerle skorla" yolu yok, risk uydurulmaz (CLAUDE.md §4)."""
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

    assert assessment.risk_level is None
    assert assessment.is_within_profile is None
    assert assessment.causes is None
    assert assessment.scenarios == []
    assert assessment.metrics.annualized_volatility_percent is None
    assert assessment.metrics.value_at_risk_try is None
    assert assessment.metrics.sharpe_ratio is None
    assert assessment.metrics.category_correlation_matrix == []
    assert assessment.metrics.asset_metrics == []
    assert any("en az" in w for w in assessment.warnings)


def test_get_risk_assessment_full_scenario_computes_category_stats(db_session):
    """Yeterli ortak fiyat gunu (>= risk_min_price_points) olan iki
    kategorili (Hisse/Altin) bir portfoy: kategori bazli volatilite/
    korelasyon/RC%/DR hesaplanmali, risk kullanicinin (Korumaci) hedef
    bandinin (0-%10) cok uzerinde oldugu icin kok neden teshisi
    tetiklenmeli."""
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

    # esit agirlik: max_asset_weight %50, HHI 0.5^2+0.5^2=0.5
    assert metrics.max_asset_weight_percent == Decimal("50.00")
    assert metrics.herfindahl_index == Decimal("0.5000")

    # kategori bazli metrikler: 5 kategorinin tumu listelenir (bos olanlar
    # dahil), yalnizca elde tutulanlarin volatilite/RC%'si dolu olur.
    assert len(metrics.category_metrics) == 5
    by_class = {m.asset_class: m for m in metrics.category_metrics}
    assert by_class[AssetClass.STOCK].weight_percent == Decimal("50.00")
    assert by_class[AssetClass.PRECIOUS_METAL].weight_percent == Decimal("50.00")
    assert by_class[AssetClass.STOCK].annualized_volatility_percent is not None
    assert by_class[AssetClass.PRECIOUS_METAL].annualized_volatility_percent is not None
    assert by_class[AssetClass.CASH].weight_percent == Decimal("0.00")
    assert by_class[AssetClass.CASH].annualized_volatility_percent is None

    # Varlik duzeyi kirilim: elde tutulan her varlik icin bir kayit, profil
    # disi olsa DAHI (asset_metrics is_within_profile'dan bagimsiz hesaplanir
    # — bkz. test_get_risk_assessment_asset_metrics_populated_when_within_profile).
    assert len(metrics.asset_metrics) == 2
    asset_by_symbol = {m.asset_symbol: m for m in metrics.asset_metrics}
    assert asset_by_symbol["TST"].asset_class == AssetClass.STOCK
    assert asset_by_symbol["TST"].weight_percent == Decimal("50.00")
    assert asset_by_symbol["TST"].annualized_volatility_percent is not None
    assert asset_by_symbol["TST"].risk_level is not None
    assert asset_by_symbol["TAU"].asset_class == AssetClass.PRECIOUS_METAL
    assert asset_by_symbol["TAU"].weight_percent == Decimal("50.00")

    # tek kategori cifti: Hisse-Altin
    assert len(metrics.category_correlation_matrix) == 1
    pair = metrics.category_correlation_matrix[0]
    assert Decimal(-1) <= pair.correlation <= Decimal(1)
    assert metrics.diversification_ratio is not None
    assert not any("en az" in w for w in assessment.warnings)

    assert assessment.risk_level is not None
    # ~%28 yillik volatilite -> Orta-Yuksek (0.20-0.30 bandi)
    assert assessment.risk_level == RiskLevel.MEDIUM_HIGH

    # Korumaci profilin hedef bandi (0-%10) cok asildigi icin profil disi
    # ve kok neden teshisi dolu olmali.
    assert assessment.is_within_profile is False
    assert assessment.causes is not None
    # tek varlik agirligi (%50) ve HHI (0.5) esiklerin (0.35 / 0.25) uzerinde.
    assert assessment.causes.concentration.triggered is True
    # Altin'in yillik volatilitesi (~%46) esigin (0.35) uzerinde ve agirligi
    # (%50) esigin (0.30) uzerinde.
    assert assessment.causes.high_volatility_asset.triggered is True
    # Hisse-Altin korelasyonu cok dusuk (~0.05), DR (~1.36) de esigin
    # (1.10) uzerinde -> korelasyon nedeni tetiklenmez.
    assert assessment.causes.correlation.triggered is False

    # include_scenarios verilmedigi icin senaryo uretilmez (varsayilan kapali).
    assert assessment.scenarios == []


def test_get_risk_assessment_asset_metrics_populated_when_within_profile(db_session):
    """Varlik duzeyi kirilimi yalnizca profil DISI durumda degil, HER ZAMAN
    hesaplanmali — is analistinin talebi "portfoydeki varliklarin tek tek
    risk durumu" profille uyuma bagli degil.

    Regresyon: eski kod `asset_vols`'u yalnizca `not is_within_profile`
    dalinda (kok neden teshisi icin) hesapliyordu; bu test o dalin DISINDA
    kalan (profile uyumlu) durumda asset_metrics'in bos kalmadigini kilitler.
    """
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
        rows.append(
            PriceHistory(asset_id=stock.id, price_date=day, close_price=Decimal(100 + (i % 5) - 2))
        )
        rows.append(
            PriceHistory(asset_id=gold.id, price_date=day, close_price=Decimal(50 - (i % 3) + 1))
        )
    db_session.add_all(rows)
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

    # Ayni portfoy (~%28 volatilite), ama Buyume profilinin hedef bandi
    # (%20-%30) bunu kapsiyor -> is_within_profile=True, kok neden teshisi
    # TETIKLENMEZ — eski kodda tam da bu dalda asset_metrics bos kalirdi.
    assessment = get_risk_assessment(db_session, user.id, profile_override=RiskProfile.GROWTH)

    assert assessment.is_within_profile is True
    assert assessment.causes is None

    assert len(assessment.metrics.asset_metrics) == 2
    by_symbol = {m.asset_symbol: m for m in assessment.metrics.asset_metrics}
    assert by_symbol["TST"].asset_class == AssetClass.STOCK
    assert by_symbol["TST"].annualized_volatility_percent is not None
    assert by_symbol["TST"].risk_level is not None
    assert by_symbol["TAU"].asset_class == AssetClass.PRECIOUS_METAL
    assert by_symbol["TAU"].annualized_volatility_percent is not None
    assert by_symbol["TAU"].risk_level is not None


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


def test_get_risk_assessment_includes_cash_in_category_weight(db_session):
    """Nakit (defterden) toplam degere VE CASH kategori agirligina dahil
    edilmeli — v2'de nakit de RISK_MAX_CATEGORY_WEIGHT/RISK_DEFENSE_FLOOR'u
    olan bir kategoridir, v1'deki gibi hesap disi birakilmiyor."""
    user, portfolio = _make_user_and_portfolio(db_session)
    stock = Asset(symbol="TST", name="Test Hisse", asset_class=AssetClass.STOCK, currency="TRY")
    db_session.add(stock)
    db_session.flush()

    start = date(2026, 1, 1)
    rows = [
        PriceHistory(
            asset_id=stock.id,
            price_date=start + timedelta(days=i),
            close_price=Decimal(100 + (i % 5) - 2),
        )
        for i in range(40)
    ]
    db_session.add_all(rows)
    db_session.add(
        Holding(
            portfolio_id=portfolio.id,
            asset_id=stock.id,
            quantity=Decimal(10),
            avg_cost_price=Decimal(95),
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

    # hisse 10*102 (son gun fiyati) + nakit 500 = 1520
    assert assessment.total_value == Decimal("1520.00")
    cash_metrics = next(
        m for m in assessment.metrics.category_metrics if m.asset_class == AssetClass.CASH
    )
    # 500 / 1520 = %32.89
    assert cash_metrics.weight_percent == Decimal("32.89")
    # nakit fiyatlanan bir varlik degildir, getiri serisine katkisi sifirdir
    # -> kategori volatilitesi 0 (None degil, hesaplanamadigi icin degil,
    # gercekten volatil olmadigi icin).
    assert cash_metrics.annualized_volatility_percent == Decimal("0.00")


def test_get_risk_assessment_scenarios_disabled_by_default(db_session, monkeypatch):
    """URUN SAHIBI KARARI (2026-08): senaryo motoru urun kapsaminda degil.
    settings.risk_scenarios_enabled varsayilan olarak False'tur; caller
    include_scenarios=True verse BILE scenarios her zaman bos donmeli."""
    monkeypatch.setattr(settings, "risk_scenarios_enabled", False)
    user, portfolio = _make_user_and_portfolio(db_session, risk_profile=RiskProfile.CONSERVATIVE)
    stock = Asset(symbol="TST", name="Test Hisse", asset_class=AssetClass.STOCK, currency="TRY")
    bond = Asset(symbol="TVL", name="Test Tahvil", asset_class=AssetClass.BOND, currency="TRY")
    db_session.add_all([stock, bond])
    db_session.flush()

    start = date(2026, 1, 1)
    rows = []
    for i in range(40):
        day = start + timedelta(days=i)
        rows.append(
            PriceHistory(asset_id=stock.id, price_date=day, close_price=Decimal(100 + (i % 5) - 2))
        )
        rows.append(
            PriceHistory(
                asset_id=bond.id,
                price_date=day,
                close_price=Decimal("20") + Decimal("0.01") * i,
            )
        )
    db_session.add_all(rows)
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
                asset_id=bond.id,
                quantity=Decimal(20),
                avg_cost_price=Decimal(18),
            ),
        ]
    )
    db_session.commit()

    assessment = get_risk_assessment(db_session, user.id, include_scenarios=True)

    assert assessment.is_within_profile is False  # kok neden teshisi hala calisiyor
    assert assessment.causes is not None
    assert assessment.scenarios == []  # ama senaryo hicbir zaman uretilmiyor


def test_get_risk_assessment_generates_scenarios_when_flag_enabled(db_session, monkeypatch):
    """Motor kod olarak duruyor: settings.risk_scenarios_enabled=True
    yapilirsa (ornegin ileride PO karari degisirse) VE include_scenarios=True
    ise, profil disi bir portfoyde en az bir yeniden dengeleme senaryosu
    uretilmeli — Aksiyon A (Hisse'nin Korumaci kategori sinirini asmasi)
    icin gecerli bir alici (Tahvil, zaten elde tutuluyor ve limitin cok
    altinda) mevcut."""
    monkeypatch.setattr(settings, "risk_scenarios_enabled", True)
    user, portfolio = _make_user_and_portfolio(db_session, risk_profile=RiskProfile.CONSERVATIVE)
    stock = Asset(symbol="TST", name="Test Hisse", asset_class=AssetClass.STOCK, currency="TRY")
    bond = Asset(symbol="TVL", name="Test Tahvil", asset_class=AssetClass.BOND, currency="TRY")
    db_session.add_all([stock, bond])
    db_session.flush()

    start = date(2026, 1, 1)
    rows = []
    for i in range(40):
        day = start + timedelta(days=i)
        rows.append(
            PriceHistory(asset_id=stock.id, price_date=day, close_price=Decimal(100 + (i % 5) - 2))
        )
        # Tahvil: gercekci sekilde DUSUK volatiliteli, yumusak dogrusal bir
        # artis (Hisse'nin aksine ani sicramalar yok) — Aksiyon A'nin
        # yuksek-riskliden dusuk-riskliye aktarim yaptigini net gostersin diye.
        rows.append(
            PriceHistory(
                asset_id=bond.id,
                price_date=day,
                close_price=Decimal("20") + Decimal("0.01") * i,
            )
        )
    db_session.add_all(rows)

    # hisse agirlikli (Korumaci sinirini (%25) cok asan) bir portfoy: hisse
    # 10*102=1020 (~%71), tahvil 20*20.39=407.80 (~%29) -> toplam ~1427.80
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
                asset_id=bond.id,
                quantity=Decimal(20),
                avg_cost_price=Decimal(18),
            ),
        ]
    )
    db_session.commit()

    assessment = get_risk_assessment(db_session, user.id, include_scenarios=True)

    assert assessment.is_within_profile is False
    assert assessment.scenarios  # en az bir senaryo bulunmali

    for scenario in assessment.scenarios:
        assert scenario.actions_applied  # bos kombinasyon dondurulmez
        assert scenario.label in ("Küçük Düzeltme", "Dengeli Düzeltme", "Belirgin Düzeltme")
        # KK-2: paylasilan turnover butcesi 30 puani asamaz.
        assert Decimal("0") < scenario.turnover_percent <= Decimal("30.5")
        # KK-4: kategori agirliklari (yuvarlama payi disinda) %100'e yakin
        # toplanmali.
        total_after = sum(cw.proposed_percent for cw in scenario.category_weights)
        assert Decimal("99") <= total_after <= Decimal("101")

    # Aksiyon A (yogunlasmayi kirmak — Hisse Korumaci sinirini asiyor, tek
    # gecerli alici olan Tahvil'e aktarim yapiyor) uretilen senaryolardan en
    # az birinde bulunmali. B/C ile ayni donor/receiver'a yakinsayabilir ve
    # dedup sonrasi tek bir sonucta birlesebilir; bu yuzden ozellikle EN
    # yuksek skorlu senaryoyu degil, en az bir senaryoyu kontrol ediyoruz.
    assert any("A" in s.actions_applied for s in assessment.scenarios)
