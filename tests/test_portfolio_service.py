import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal

import pytest

from app.core.config import AssetClass
from app.core.exceptions import NotFoundError
from app.models import Asset, Portfolio, PriceHistory, TransactionType, User
from app.services.ledger_service import rebuild_holdings, record_transaction
from app.services.portfolio_service import get_portfolio_summary

_BUY_DAY = date(2026, 1, 1)


def _tx_dt(day: date) -> datetime:
    return datetime.combine(day, time(hour=12), tzinfo=timezone.utc)


def _seed_portfolio(db_session, email: str, deposit: Decimal):
    """Hisse ve altın tutan bir portföyü DEFTERDEN kurar.

    Holdings doğrudan yazılmaz: `docs/DATA.md` §2 "holdings'i yalnızca
    rebuild_holdings yazar" der ve serbest nakit ancak defter varsa oluşur —
    holdings'i elle yazan eski kurulum, nakit yolunu hiç egzersiz etmediği
    için getiri hatasını yıllarca görünmez kılmıştı.

    Alımlar: hisse 10 adet × 90 TL = 900, altın 5 adet × 60 TL = 300.
    Güncel fiyatlar: hisse 100 (kâr), altın 50 (zarar).
    """
    user = User(email=email, full_name="Test User")
    stock = Asset(symbol="TST", name="Test Hisse", asset_class=AssetClass.STOCK, currency="TRY")
    gold = Asset(
        symbol="TAU", name="Test Altin", asset_class=AssetClass.PRECIOUS_METAL, currency="TRY"
    )
    db_session.add_all([user, stock, gold])
    db_session.flush()

    portfolio = Portfolio(user_id=user.id)
    db_session.add(portfolio)
    db_session.flush()

    db_session.add_all(
        [
            PriceHistory(
                asset_id=stock.id, price_date=date(2026, 1, 1), close_price=Decimal("90.00")
            ),
            PriceHistory(
                asset_id=stock.id, price_date=date(2026, 1, 2), close_price=Decimal("100.00")
            ),
            PriceHistory(
                asset_id=gold.id, price_date=date(2026, 1, 1), close_price=Decimal("50.00")
            ),
        ]
    )
    db_session.flush()

    record_transaction(
        db_session,
        portfolio.id,
        TransactionType.DEPOSIT,
        transaction_date=_tx_dt(_BUY_DAY),
        cash_amount_try=deposit,
    )
    for asset, quantity, price in (
        (stock, Decimal(10), Decimal("90.00")),
        (gold, Decimal(5), Decimal("60.00")),
    ):
        record_transaction(
            db_session,
            portfolio.id,
            TransactionType.BUY,
            transaction_date=_tx_dt(_BUY_DAY),
            asset_id=asset.id,
            quantity=quantity,
            price=price,
        )
    rebuild_holdings(db_session, portfolio.id)
    db_session.commit()
    return user


def test_get_portfolio_summary_computes_value_allocation_and_gain(db_session):
    """Tamamı yatırıma dönmüş portföy (serbest nakit yok)."""
    user = _seed_portfolio(db_session, "test@example.com", deposit=Decimal("1200.00"))

    summary = get_portfolio_summary(db_session, user.id)

    assert summary.holdings_count == 2
    # stock: 10 * en guncel fiyat (100.00) = 1000; gold: 5 * 50.00 = 250
    assert summary.total_value == Decimal("1250.00")
    # stock cost: 10*90=900; gold cost: 5*60=300
    assert summary.total_cost_basis == Decimal("1200.00")
    # tamami yatirildi -> yatirilan sermaye = varlik maliyeti
    assert summary.net_invested == Decimal("1200.00")
    assert summary.total_gain_loss.amount == Decimal("50.00")
    assert summary.total_gain_loss.percent == Decimal("4.17")  # 50/1200*100, 2 ondalik

    allocation_by_class = {item.asset_class: item for item in summary.allocation}
    assert allocation_by_class[AssetClass.STOCK].value == Decimal("1000.00")
    assert allocation_by_class[AssetClass.STOCK].percent == Decimal("80.00")
    assert allocation_by_class[AssetClass.PRECIOUS_METAL].value == Decimal("250.00")
    assert allocation_by_class[AssetClass.PRECIOUS_METAL].percent == Decimal("20.00")

    # en guncel fiyatin tarihi (stock icin 2 Ocak) as_of olarak yansimali
    assert summary.as_of == date(2026, 1, 2)


def test_ak_5_11_free_cash_is_not_reported_as_gain(db_session):
    """Yatırıma dönüşmemiş nakit kâr sayılmamalı (FR-3).

    1500 yatırılıp 1200'ü yatırıma dönmüş; 300 TL hesapta duruyor. Bu 300 TL
    toplam değere girer (kullanıcının parasıdır) ama kazanç DEĞİLDİR.

    Regresyon: taban `total_cost_basis` (1200) iken kâr 350 TL / +%29,17
    çıkıyordu — serbest nakdin tamamı kâr sayılıyordu. Canlıda ölçülen etki:
    1.87M yatırmış bir portföyde getiri %43,37 yerine %59,36 görünüyordu.
    """
    user = _seed_portfolio(db_session, "freecash@example.com", deposit=Decimal("1500.00"))

    summary = get_portfolio_summary(db_session, user.id)

    # 1000 (hisse) + 250 (altin) + 300 (serbest nakit)
    assert summary.total_value == Decimal("1550.00")
    assert summary.total_cost_basis == Decimal("1200.00"), "varlık maliyeti nakdi içermez"
    assert summary.net_invested == Decimal("1500.00"), "yatırılan sermaye nakdi içerir"

    # Kazanç yalnızca fiyat hareketinden: +100 hisse, -50 altin.
    assert summary.total_gain_loss.amount == Decimal("50.00")
    assert summary.total_gain_loss.percent == Decimal("3.33")  # 50/1500*100

    # Ozdeslik: deger - yatirilan = kar. Ekrandaki uc rakam birbirini tutmali.
    assert summary.total_value - summary.net_invested == summary.total_gain_loss.amount

    # Serbest nakit 'cash' diliminde gorunur.
    cash = next(i for i in summary.allocation if i.asset_class == AssetClass.CASH)
    assert cash.value == Decimal("300.00")


def test_get_portfolio_summary_raises_not_found_for_unknown_user(db_session):
    with pytest.raises(NotFoundError):
        get_portfolio_summary(db_session, uuid.uuid4())


def test_oldest_price_date_reports_the_stalest_price_used(db_session):
    """Özet en TAZE fiyat gününü yazıyor; en eskisi de raporlanmalı.

    Her varlık kendi son fiyatıyla değerlenir. Fixture'da hisse 2 Ocak'ta,
    altın 1 Ocak'ta fiyatlanmış; `as_of` yalnızca 2 Ocak'ı gösterirse özet
    olduğundan taze görünür (CLAUDE.md §4).
    """
    user = _seed_portfolio(db_session, "stale@example.com", deposit=Decimal("1200.00"))

    summary = get_portfolio_summary(db_session, user.id)

    assert summary.as_of == date(2026, 1, 2)
    assert summary.oldest_price_date == date(2026, 1, 1)


def test_withdrawal_does_not_inflate_return(db_session):
    """Çekim yapılmış portföyde oranın paydası TOPLAM YATIRILAN olmalı.

    1.000 yatırılıp 900'ü yatırıma dönmüş, hisse 900 → 1.000'e çıkmış, sonra
    100 çekilmiş:

        değer          = 1.000   (yalnızca hisse; nakit çekildi)
        net sermaye    =   900   (1.000 yatırma - 100 çekme)
        toplam yatırma = 1.000

    Kazanç 100 TL ve para %10 büyüdü. Net sermaye payda alınsaydı
    100/900 = %11,11 çıkardı — çekilen para hiç yatırılmamış gibi sayılırdı.
    """
    user = User(email="withdraw@example.com", full_name="Test Withdraw")
    stock = Asset(symbol="TSW", name="Test Hisse", asset_class=AssetClass.STOCK, currency="TRY")
    db_session.add_all([user, stock])
    db_session.flush()
    portfolio = Portfolio(user_id=user.id)
    db_session.add(portfolio)
    db_session.flush()

    db_session.add_all(
        [
            PriceHistory(
                asset_id=stock.id, price_date=date(2026, 1, 1), close_price=Decimal("90.00")
            ),
            PriceHistory(
                asset_id=stock.id, price_date=date(2026, 1, 2), close_price=Decimal("100.00")
            ),
        ]
    )
    db_session.flush()

    record_transaction(
        db_session,
        portfolio.id,
        TransactionType.DEPOSIT,
        transaction_date=_tx_dt(_BUY_DAY),
        cash_amount_try=Decimal("1000.00"),
    )
    record_transaction(
        db_session,
        portfolio.id,
        TransactionType.BUY,
        transaction_date=_tx_dt(_BUY_DAY),
        asset_id=stock.id,
        quantity=Decimal(10),
        price=Decimal("90.00"),
    )
    record_transaction(
        db_session,
        portfolio.id,
        TransactionType.WITHDRAW,
        transaction_date=_tx_dt(_BUY_DAY),
        cash_amount_try=Decimal("-100.00"),
    )
    rebuild_holdings(db_session, portfolio.id)
    db_session.commit()

    summary = get_portfolio_summary(db_session, user.id)

    assert summary.total_value == Decimal("1000.00"), "nakit çekildi, geriye hisse kaldı"
    assert summary.net_invested == Decimal("900.00")
    assert summary.total_gain_loss.amount == Decimal("100.00")
    assert summary.total_gain_loss.percent == Decimal("10.00"), "payda toplam yatırılan olmalı"
