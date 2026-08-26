"""Faz 2 portföy hesaplarının testleri.

Senaryolar elle hesaplanabilecek kadar küçük tutuldu: her beklenen değerin
nereden geldiği yorumda yazıyor. Amaç "çalışıyor mu" değil, "doğru sayıyı mı
üretiyor" sorusunu cevaplamak.

Takvim notu: 2026-01-01 Perşembe. 03-04 Ocak hafta sonu; seriden düşmeleri
beklenir (bkz. get_portfolio_performance hafta sonu kuralı).
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.core.config import AssetClass, Granularity, TimeWindow
from app.core.exceptions import InsufficientDataError, NotFoundError, ValidationAppError
from app.models import (
    Asset,
    Holding,
    Portfolio,
    PriceHistory,
    Transaction,
    TransactionType,
    User,
)
from app.services.portfolio_service import (
    get_benchmark_comparison,
    get_holdings_valuation,
    get_portfolio_performance,
    get_transactions,
)


def _tx(portfolio_id, tx_type, day, *, asset_id=None, quantity="0", cash="0", price=None):
    return Transaction(
        portfolio_id=portfolio_id,
        asset_id=asset_id,
        transaction_type=tx_type,
        quantity=Decimal(quantity),
        price=None if price is None else Decimal(price),
        currency="TRY",
        fx_rate_to_try=Decimal(1),
        cash_amount_try=Decimal(cash),
        transaction_date=datetime(day.year, day.month, day.day, 10, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# get_holdings_valuation
# ---------------------------------------------------------------------------


@pytest.fixture()
def valuation_fixture(db_session):
    """TRY varlık + döviz cinsi varlık + fiyatı hiç olmayan varlık."""
    user = User(email="val@example.com", full_name="Val")
    stock = Asset(symbol="TST", name="Test Hisse", asset_class=AssetClass.STOCK, currency="TRY")
    foreign = Asset(
        symbol="FRGN", name="Yabanci Hisse", asset_class=AssetClass.STOCK, currency="USD"
    )
    missing = Asset(symbol="MISS", name="Fiyatsiz", asset_class=AssetClass.BOND, currency="TRY")
    usdtry = Asset(
        symbol="USDTRY", name="Amerikan Dolari", asset_class=AssetClass.CURRENCY, currency="TRY"
    )
    db_session.add_all([user, stock, foreign, missing, usdtry])
    db_session.flush()

    portfolio = Portfolio(user_id=user.id)
    db_session.add(portfolio)
    db_session.flush()

    db_session.add_all(
        [
            PriceHistory(
                asset_id=stock.id, price_date=date(2026, 1, 2), close_price=Decimal("100")
            ),
            PriceHistory(
                asset_id=foreign.id, price_date=date(2026, 1, 2), close_price=Decimal("20")
            ),
            PriceHistory(
                asset_id=usdtry.id, price_date=date(2026, 1, 2), close_price=Decimal("40")
            ),
            # MISS icin bilerek fiyat yok.
            Holding(
                portfolio_id=portfolio.id,
                asset_id=stock.id,
                quantity=Decimal(10),
                avg_cost_price=Decimal("90"),
            ),
            Holding(
                portfolio_id=portfolio.id,
                asset_id=foreign.id,
                quantity=Decimal(5),
                avg_cost_price=Decimal("200"),
            ),
            Holding(
                portfolio_id=portfolio.id,
                asset_id=missing.id,
                quantity=Decimal(2),
                avg_cost_price=Decimal("50"),
            ),
        ]
    )
    db_session.commit()
    return user


def test_holdings_valuation_converts_fx_and_computes_weights(db_session, valuation_fixture):
    result = get_holdings_valuation(db_session, valuation_fixture.id)
    rows = {row.symbol: row for row in result.holdings}

    # TST: 10 x 100 = 1.000 TL deger, maliyet 10 x 90 = 900, K/Z 100 -> %11,11
    assert rows["TST"].market_value_try == Decimal("1000.00")
    assert rows["TST"].cost_basis_try == Decimal("900.00")
    assert rows["TST"].unrealized_pnl_try == Decimal("100.00")
    assert rows["TST"].unrealized_pnl_percent == Decimal("11.11")

    # FRGN: 20 USD x 40 TL/USD = 800 TL birim -> 5 x 800 = 4.000 TL
    assert rows["FRGN"].current_price_try == Decimal("800.00")
    assert rows["FRGN"].market_value_try == Decimal("4000.00")

    # Payda nakit dahil toplam deger; burada nakit yok -> 1.000 + 4.000 = 5.000
    assert rows["TST"].weight_percent == Decimal("20.00")
    assert rows["FRGN"].weight_percent == Decimal("80.00")


def test_holdings_valuation_marks_missing_price_without_inventing_value(
    db_session, valuation_fixture
):
    result = get_holdings_valuation(db_session, valuation_fixture.id)
    missing = next(row for row in result.holdings if row.symbol == "MISS")

    # Eksik veri 0 ile doldurulmaz (AK 5.5): satir durur, degerler None.
    assert missing.price_missing is True
    assert missing.market_value_try is None
    assert missing.weight_percent is None
    assert missing.unrealized_pnl_percent is None
    assert result.excluded_symbols == ["MISS"]
    # Fiyatsiz satir agirlik paydasina da girmemeli.
    assert sum(r.weight_percent for r in result.holdings if r.weight_percent is not None) == (
        Decimal("100.00")
    )


def test_holdings_valuation_ranks_performers_in_code(db_session, valuation_fixture):
    result = get_holdings_valuation(db_session, valuation_fixture.id)
    # FRGN %300 (800 vs 200), TST %11,11 -> siralama LLM'e birakilmaz.
    assert result.best_performer.symbol == "FRGN"
    assert result.best_performer.unrealized_pnl_percent == Decimal("300.00")
    assert result.worst_performer.symbol == "TST"


def test_holdings_valuation_raises_not_found(db_session):
    with pytest.raises(NotFoundError):
        get_holdings_valuation(db_session, uuid.uuid4())


# ---------------------------------------------------------------------------
# get_transactions
# ---------------------------------------------------------------------------


@pytest.fixture()
def ledger_fixture(db_session):
    user = User(email="ledger@example.com", full_name="Ledger")
    stock = Asset(symbol="TST", name="Test Hisse", asset_class=AssetClass.STOCK, currency="TRY")
    db_session.add_all([user, stock])
    db_session.flush()

    portfolio = Portfolio(user_id=user.id)
    db_session.add(portfolio)
    db_session.flush()

    db_session.add_all(
        [
            _tx(portfolio.id, TransactionType.DEPOSIT, date(2026, 1, 1), cash="10000"),
            _tx(
                portfolio.id,
                TransactionType.BUY,
                date(2026, 1, 2),
                asset_id=stock.id,
                quantity="10",
                cash="-1000",
                price="100",
            ),
            _tx(
                portfolio.id,
                TransactionType.BUY,
                date(2026, 1, 5),
                asset_id=stock.id,
                quantity="5",
                cash="-550",
                price="110",
            ),
            _tx(
                portfolio.id,
                TransactionType.SELL,
                date(2026, 1, 6),
                asset_id=stock.id,
                quantity="3",
                cash="+360",
                price="120",
            ),
        ]
    )
    db_session.commit()
    return user, stock


def test_transactions_position_counts_from_ledger_start_despite_filter(db_session, ledger_fixture):
    user, _stock = ledger_fixture
    result = get_transactions(db_session, user.id, start_date=date(2026, 1, 5))

    # Filtre 5 Ocak'tan basliyor ama pozisyon defterin BASINDAN sayilmali:
    # 2 Ocak'ta 10 alindi, 5 Ocak'ta +5 -> 15, 6 Ocak'ta -3 -> 12.
    assert [row.position_after for row in result.transactions] == [Decimal(15), Decimal(12)]
    assert len(result.transactions) == 2


def test_transactions_symbol_filter_drops_cash_movements(db_session, ledger_fixture):
    user, _stock = ledger_fixture
    result = get_transactions(db_session, user.id, symbols=["tst"])

    # Sembol suzgeci verildiginde para yatirma kaydi listeye girmez;
    # sembol kucuk harfle verilse de eslesmeli.
    assert {row.type for row in result.transactions} == {
        TransactionType.BUY,
        TransactionType.SELL,
    }
    assert all(row.symbol == "TST" for row in result.transactions)


def test_transactions_without_filter_includes_cash_and_is_chronological(db_session, ledger_fixture):
    user, _stock = ledger_fixture
    result = get_transactions(db_session, user.id)

    assert len(result.transactions) == 4
    assert result.transactions[0].type == TransactionType.DEPOSIT
    assert result.transactions[0].symbol is None
    assert result.transactions[0].position_after is None
    dates = [row.transaction_date for row in result.transactions]
    assert dates == sorted(dates)


def test_transactions_rejects_reversed_date_range(db_session, ledger_fixture):
    user, _stock = ledger_fixture
    with pytest.raises(ValidationAppError):
        get_transactions(
            db_session, user.id, start_date=date(2026, 2, 1), end_date=date(2026, 1, 1)
        )


# ---------------------------------------------------------------------------
# get_portfolio_performance / get_benchmark_comparison
# ---------------------------------------------------------------------------


@pytest.fixture()
def performance_fixture(db_session):
    """1 Ocak'ta 1.000 TL ile 10 adet alinir; 9 Ocak'ta fiyat 130 olur.

    Dis akis yalnizca ilk gun oldugu icin TWR = 1300/1000 - 1 = %30.
    """
    user = User(email="perf@example.com", full_name="Perf")
    stock = Asset(symbol="TST", name="Test Hisse", asset_class=AssetClass.STOCK, currency="TRY")
    gold = Asset(
        symbol="XAUTRY", name="Gram Altin", asset_class=AssetClass.PRECIOUS_METAL, currency="TRY"
    )
    db_session.add_all([user, stock, gold])
    db_session.flush()

    portfolio = Portfolio(user_id=user.id)
    db_session.add(portfolio)
    db_session.flush()

    fiyatlar = {
        date(2026, 1, 1): "100",
        date(2026, 1, 2): "110",
        date(2026, 1, 5): "120",
        date(2026, 1, 6): "120",
        date(2026, 1, 7): "120",
        date(2026, 1, 8): "120",
        date(2026, 1, 9): "130",
    }
    db_session.add_all(
        [
            PriceHistory(asset_id=stock.id, price_date=gun, close_price=Decimal(deger))
            for gun, deger in fiyatlar.items()
        ]
        + [
            PriceHistory(
                asset_id=gold.id, price_date=date(2026, 1, 1), close_price=Decimal("1000")
            ),
            PriceHistory(
                asset_id=gold.id, price_date=date(2026, 1, 9), close_price=Decimal("1100")
            ),
            _tx(portfolio.id, TransactionType.DEPOSIT, date(2026, 1, 1), cash="1000"),
            _tx(
                portfolio.id,
                TransactionType.BUY,
                date(2026, 1, 1),
                asset_id=stock.id,
                quantity="10",
                cash="-1000",
                price="100",
            ),
        ]
    )
    db_session.commit()
    return user


def test_performance_strips_external_flows_and_drops_weekends(db_session, performance_fixture):
    result = get_portfolio_performance(db_session, performance_fixture.id, TimeWindow.M1)

    assert result.granularity is Granularity.DAILY
    # 1,2,5,6,7,8,9 Ocak -> 7 is gunu; 3-4 Ocak hafta sonu seride yok.
    assert [point.date.day for point in result.series] == [1, 2, 5, 6, 7, 8, 9]

    # Baslangic sermayesi ilk gunun akisi; donem ici giris yok.
    assert result.summary.start_value == Decimal("1000.00")
    assert result.summary.end_value == Decimal("1300.00")
    assert result.summary.change_amount == Decimal("300.00")
    assert result.summary.change_percent == Decimal("30.00")
    assert result.summary.unrealized_pnl == Decimal("300.00")

    # Kumulatif yatirilan para sabit kalir; grafikteki bosluk toplam kardir.
    assert {point.invested_try for point in result.series} == {Decimal("1000.00")}


def test_performance_period_changes_return_none_when_data_is_short(db_session, performance_fixture):
    result = get_portfolio_performance(db_session, performance_fixture.id, TimeWindow.M1)

    # 8 -> 9 Ocak: 1300/1200 - 1 = %8,33
    assert result.summary.changes.daily == Decimal("8.33")
    # 2 -> 9 Ocak: 1300/1100 - 1 = %18,18
    assert result.summary.changes.weekly == Decimal("18.18")
    # 30 gunluk gecmis yok -> 0 degil None.
    assert result.summary.changes.monthly is None


def test_performance_marks_window_truncated_to_inception(db_session, performance_fixture):
    result = get_portfolio_performance(db_session, performance_fixture.id, TimeWindow.M1)
    # Portfoy 1 Ocak'ta baslamis, 1 aylik pencere daha geriye uzaniyor.
    assert result.truncated_to_inception is True
    assert result.inception == date(2026, 1, 1)
    # Seri son FIYAT gununde biter, bugunde degil.
    assert result.as_of == date(2026, 1, 9)


def test_performance_raises_when_portfolio_has_no_transactions(db_session):
    user = User(email="bos@example.com", full_name="Bos")
    db_session.add(user)
    db_session.flush()
    db_session.add(Portfolio(user_id=user.id))
    db_session.commit()

    with pytest.raises(InsufficientDataError):
        get_portfolio_performance(db_session, user.id, TimeWindow.M1)


def test_benchmark_freezes_t0_quantities_and_compares_with_index(db_session, performance_fixture):
    result = get_benchmark_comparison(db_session, performance_fixture.id, TimeWindow.M1)

    # t0 = 1 Ocak: 10 adet x 100 = 1.000 maliyet, t1 = 9 Ocak: 10 x 130 = 1.300
    assert result.portfolio_return_percent == Decimal("30.00")
    assert [c.asset_class for c in result.by_asset_class] == [AssetClass.STOCK]
    assert result.by_asset_class[0].return_percent == Decimal("30.00")

    endeksler = {entry.symbol: entry.return_percent for entry in result.benchmarks}
    # XAUTRY 1000 -> 1100 = %10. XU100 evrende yok, listeye hic girmez.
    assert endeksler == {"XAUTRY": Decimal("10.00")}
    assert result.excluded_symbols == []


# ---------------------------------------------------------------------------
# Karsilastirmali getiri karti: YTD penceresi, EUR cubugu, nakit-once fonlama
# ---------------------------------------------------------------------------


def test_benchmark_semboller_kartin_bes_cubuguyla_ortusuyor():
    """Kart BES cubuk gosteriyor: portfoy + BIST100 + USD + EUR + Altin.

    EURTRY listeye 26 Agustos 2026'da eklendi; oncesinde uc sembol vardi ve
    euro cubugu gercek veriye baglanamiyordu. Sira kartta soldan saga aynen
    korunur, bu yuzden tuple olarak kilitleniyor.
    """
    from app.services.portfolio_service import BENCHMARK_SYMBOLS

    assert BENCHMARK_SYMBOLS == ("XU100", "USDTRY", "EURTRY", "XAUTRY")


def test_ytd_penceresi_1_ocaktan_baslar(db_session, performance_fixture):
    """YTD digerlerinin aksine SABIT UZUNLUKTA DEGIL.

    `WINDOW_DAYS` sozlugunde yeri yok; `window_start_date` onu ayri ele
    aliyor. Sabit gun sayilsaydi ocak ayinda gecen yila tasardi.
    """
    result = get_benchmark_comparison(db_session, performance_fixture.id, TimeWindow.YTD)

    assert result.start_date == date(2026, 1, 1)
    assert result.window is TimeWindow.YTD


def test_window_start_date_ytd_yil_basini_verir():
    from app.services.price_service import window_start_date

    assert window_start_date(TimeWindow.YTD, date(2026, 8, 26)) == date(2026, 1, 1)
    # Yilin ilk gunu: pencere sifir uzunlukta, gecen yila TASMAZ.
    assert window_start_date(TimeWindow.YTD, date(2026, 1, 1)) == date(2026, 1, 1)
    # Sabit pencereler eskisi gibi.
    assert window_start_date(TimeWindow.M1, date(2026, 8, 26)) == date(2026, 7, 27)


def test_benchmark_nakit_once_yatirilmissa_da_calisir(db_session):
    """Portfoy once nakitle fonlanip varlik GUNLER SONRA alinabilir.

    Baslangic `min(transaction_date)` alindiginda o gun DEPOSIT gunu oluyordu
    ve `position_as_of` orada bos donuyordu — hicbir varlik yoktu. Olculdu:
    12 aylik pencerede seed'li 50 kullanicinin 50'si de InsufficientDataError
    aliyordu, yani kartin "Yillik" dugmesi hicbir kullanicida calismiyordu.

    Dogrusu ILK VARLIK ALIMI: fiyat getirisi, hicbir seye sahip olmadigin bir
    gunden olculemez.
    """
    user = User(email="nakit-once@example.com", full_name="Nakit Once")
    stock = Asset(symbol="TST2", name="Test Hisse 2", asset_class=AssetClass.STOCK, currency="TRY")
    db_session.add_all([user, stock])
    db_session.flush()

    portfolio = Portfolio(user_id=user.id)
    db_session.add(portfolio)
    db_session.flush()

    db_session.add_all(
        [
            PriceHistory(
                asset_id=stock.id, price_date=date(2026, 1, 10), close_price=Decimal("100")
            ),
            PriceHistory(
                asset_id=stock.id, price_date=date(2026, 1, 20), close_price=Decimal("150")
            ),
            # Nakit 1 Ocak'ta yatiyor, varlik 10 Ocak'ta aliniyor.
            _tx(portfolio.id, TransactionType.DEPOSIT, date(2026, 1, 1), cash="1000"),
            _tx(
                portfolio.id,
                TransactionType.BUY,
                date(2026, 1, 10),
                asset_id=stock.id,
                quantity="10",
                cash="-1000",
                price="100",
            ),
        ]
    )
    db_session.commit()

    result = get_benchmark_comparison(db_session, user.id, TimeWindow.M1)

    # Baslangic ILK ALIM gunu, nakit yatirma gunu degil.
    assert result.start_date == date(2026, 1, 10)
    assert result.truncated_to_inception is True
    # 100 -> 150 = %50
    assert result.portfolio_return_percent == Decimal("50.00")
