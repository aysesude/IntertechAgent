"""Veri katmanı değişmezleri (invariant) — DB-PLANI §6 ve kabul kriterleri.

Test adları kabul kriterlerine bağlanır (izlenebilirlik zinciri):
    I1  test_ledger_reconciliation                    -> AK 5.12
    I2  test_cash_never_negative                      -> defter dengesi
    I3  test_synthetic_never_overwrites_real          -> AK 5.1, 5.5
        test_synthetic_is_not_interleaved_with_real   -> AK 5.1, FR-3, FR-4
        test_no_transaction_priced_from_synthetic_row -> FR-3
    I4  test_ak_5_3_price_source_and_timestamp        -> AK 5.3
    I5  test_ak_5_7_fx_conversion                     -> AK 5.7
    I6  test_external_flow_excluded_from_return       -> FR-3
    I7  test_derived_price_matches_factor             -> türetilmiş tutarlılık
    I8  test_fund_asset_class_follows_economic_risk   -> FR-4, AK 5.1
        test_synthetic_correlation_nonzero            -> AK-2.2, AK-2.6
        test_only_deposits_remain_synthetic           -> AK 5.1
        test_fx_conversion_has_a_subject              -> AK 5.7
"""

import math
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import AssetClass, PriceSource, RiskProfile, settings
from app.models import (
    Asset,
    Holding,
    Portfolio,
    PriceHistory,
    Transaction,
    TransactionType,
    User,
)
from app.providers.base import PricePoint
from app.providers.universe import ASSET_UNIVERSE, SPEC_BY_SYMBOL
from app.services.ledger_service import (
    LedgerError,
    cash_balance_as_of,
    rebuild_holdings,
    record_transaction,
)
from app.services.portfolio_service import get_portfolio_summary
from app.services.price_ingest import upsert_prices
from app.services.valuation_service import twr, unrealized_pnl
from data.generate_dummy import main as generate_dummy_main
from data.seed_ledger import NUM_USERS, _user_id


@pytest.fixture(scope="module")
def seeded(engine):
    """Tam seed bir kez koşar; modüldeki testler aynı veri üstünde çalışır."""
    generate_dummy_main()
    return engine


def _tx_dt(d: date) -> datetime:
    return datetime.combine(d, time(hour=12), tzinfo=timezone.utc)


def _price_on(session: Session, symbol: str, day: date) -> Decimal:
    asset_id = session.execute(select(Asset.id).where(Asset.symbol == symbol)).scalar_one()
    return session.execute(
        select(PriceHistory.close_price).where(
            PriceHistory.asset_id == asset_id, PriceHistory.price_date == day
        )
    ).scalar_one()


def _last_trading_day(session: Session) -> date:
    """Fiyatı olan son gün (ANCHOR_DATE hafta sonuna denk gelebilir)."""
    return session.execute(select(func.max(PriceHistory.price_date))).scalar_one()


def _latest_price(session: Session, symbol: str) -> Decimal:
    asset_id = session.execute(select(Asset.id).where(Asset.symbol == symbol)).scalar_one()
    return session.execute(
        select(PriceHistory.close_price)
        .where(PriceHistory.asset_id == asset_id)
        .order_by(PriceHistory.price_date.desc())
        .limit(1)
    ).scalar_one()


# --------------------------------------------------------------------------
# I1 — holdings, defterden yeniden üretilebilir olmalı (AK 5.12)
# --------------------------------------------------------------------------


def test_ledger_reconciliation(seeded):
    with Session(seeded) as session:
        portfolios = session.execute(select(Portfolio)).scalars().all()
        assert portfolios, "seed portföy üretmemiş"

        for portfolio in portfolios:
            before = {
                h.asset_id: (h.quantity, h.avg_cost_price, h.realized_pnl_try)
                for h in session.execute(
                    select(Holding).where(Holding.portfolio_id == portfolio.id)
                )
                .scalars()
                .all()
            }
            rebuild_holdings(session, portfolio.id)
            after = {
                h.asset_id: (h.quantity, h.avg_cost_price, h.realized_pnl_try)
                for h in session.execute(
                    select(Holding).where(Holding.portfolio_id == portfolio.id)
                )
                .scalars()
                .all()
            }
            assert before == after, f"holdings defterle mutabık değil: {portfolio.id}"
        session.rollback()


def test_seed_produces_every_risk_profile(seeded):
    """Dört risk profilinin de veritabanına yazıldığını doğrular.

    'growth' config'de tanımlıydı ve risk_service onun için ayrı sabitler
    taşıyordu, ama seed hiç üretmiyordu: o kod yolunun tamamı (risk hesabı,
    senaryo üretimi, arayüz gösterimi) çalışmıyor ve demoda gösterilemiyordu.
    """
    with Session(seeded) as session:
        found = set(session.execute(select(User.risk_profile)).scalars().all())
        assert found == set(RiskProfile), f"üretilmeyen profil: {set(RiskProfile) - found}"


def test_seeded_user_ids_are_stable(seeded):
    """DB'ye yazılan kimlikler _user_id ile birebir eşleşmeli."""
    with Session(seeded) as session:
        stored = set(session.execute(select(User.id)).scalars().all())
    expected = {_user_id(i) for i in range(NUM_USERS)}
    assert expected <= stored, "seed farklı kimlikler yazdı"


# --------------------------------------------------------------------------
# I2 — nakit hiçbir portföyde negatif olamaz
# --------------------------------------------------------------------------


def test_cash_never_negative(seeded):
    """Nakit HER GÜN sıfırın üstünde kalmalı, yalnızca sonda değil.

    Test önceden tek bir `cash_balance_as_of(...)` çağrısıyla yalnızca SON
    bakiyeye bakıyordu. Bir portföy dönem ortasında elinde olmayan parayı
    harcayıp sonradan gelen faiz/satışla toparlansaydı, defter o gün fiilen
    eksideyken test yeşil yanardı. Nakit hareketleri (WITHDRAW) seed'e
    eklenirken bu boşluk gerçek bir risk hâline geldi, o yüzden değişmez
    her işlem gününde denetleniyor.
    """
    with Session(seeded) as session:
        for portfolio in session.execute(select(Portfolio)).scalars().all():
            gunler = (
                session.execute(
                    select(func.date(Transaction.transaction_date))
                    .where(Transaction.portfolio_id == portfolio.id)
                    .distinct()
                )
                .scalars()
                .all()
            )
            for gun in gunler:
                if isinstance(gun, str):  # SQLite `date()` metin döndürür
                    gun = date.fromisoformat(gun)
                balance = cash_balance_as_of(session, portfolio.id, gun)
                assert balance >= 0, f"negatif nakit: {portfolio.id} @ {gun} -> {balance}"


def test_write_guard_alone_cannot_keep_the_ledger_solvent(seeded):
    """Yazma anındaki nakit koruması TARİH BİLMİYOR — bu testin sebebi o.

    `record_transaction`, negatif nakit ayağını `cash_balance_as_of(db,
    portfolio_id)` ile denetliyor: gün parametresi YOK, yani defterin
    TOPLAMINA bakıyor. Tarihi geride olan bir çekim, kendisinden SONRA
    tarihlenmiş bir yatırma sayesinde bu kapıdan geçebiliyor ve defter aradaki
    günlerde eksiye düşüyor.

    Bu bir `record_transaction` hatası değil, sınırı: tek bir satırı yazarken
    tüm zaman çizgisini yeniden denetlemek pahalı olurdu. Sınır bilindiği için
    üreten taraf (seed) çekimi `_cash_floor_from` ile boyutlandırıyor ve I2
    her işlem gününü ayrı ayrı denetliyor. Bu test o iş bölümünü kayda
    geçiriyor: koruma tek başına yetseydi ikisine de gerek olmazdı.
    """
    with Session(seeded) as session:
        user = User(email="tarih-sirasi@example.com", full_name="Sira Testi")
        session.add(user)
        session.flush()
        portfolio = Portfolio(user_id=user.id)
        session.add(portfolio)
        session.flush()

        gec_gun = datetime(2026, 3, 31, 10, tzinfo=timezone.utc)
        erken_gun = datetime(2026, 3, 1, 10, tzinfo=timezone.utc)

        record_transaction(
            session,
            portfolio.id,
            TransactionType.DEPOSIT,
            transaction_date=gec_gun,
            cash_amount_try=Decimal("100000"),
        )
        # Yatırmadan ÖNCEKİ bir güne çekim: toplam bakiye 100.000 olduğu için
        # yazma koruması buna izin veriyor.
        record_transaction(
            session,
            portfolio.id,
            TransactionType.WITHDRAW,
            transaction_date=erken_gun,
            cash_amount_try=Decimal("-80000"),
        )
        session.flush()

        # Son bakiye sağlıklı: I2'nin ESKİ hâli (yalnızca son bakiye) bunu
        # yakalayamazdı.
        assert cash_balance_as_of(session, portfolio.id) == Decimal("20000")

        # Oysa çekim gününde defter 80.000 TL ekside.
        assert cash_balance_as_of(session, portfolio.id, erken_gun.date()) == Decimal("-80000")


def test_record_transaction_rejects_overdraft(seeded):
    with Session(seeded) as session:
        user = User(email="overdraft@test.local", full_name="Test Overdraft")
        session.add(user)
        session.flush()
        portfolio = Portfolio(user_id=user.id)
        session.add(portfolio)
        session.flush()
        thyao = session.execute(select(Asset).where(Asset.symbol == "THYAO")).scalar_one()

        with pytest.raises(LedgerError):
            record_transaction(
                session,
                portfolio.id,
                TransactionType.BUY,
                transaction_date=_tx_dt(settings.anchor_date),
                asset_id=thyao.id,
                quantity=Decimal(10),
                price=Decimal("100"),
            )
        session.rollback()


# --------------------------------------------------------------------------
# I3 — sentetik, gerçek satırı asla ezemez (AK 5.1, 5.5)
# --------------------------------------------------------------------------


def test_synthetic_is_not_interleaved_with_real(seeded):
    """Gerçek serinin içinde sentetik satır kalmamalı (AK 5.1, FR-3, FR-4).

    `trading_days()` resmî tatilleri bilmiyor; BIST/TEFAS o günlerde fiyat
    yayımlamadığı için gerçek serinin ORTASINDA sentetik satırlar kalıyordu.
    Sentetik `base_price` gerçek fiyattan kat kat sapabildiğinden (ölçülen:
    TCD 5,42 vs gerçek 35,63) her delik hem sahte bir günlük getiri
    (volatilite/korelasyon/VaR/TWR bozulur) hem de sahte maliyet üretiyordu
    (defter alımı o güne düşerse). Ölçülen yayılım: 35 varlığın hepsinde
    2-10 delik, 151 işlem, 50 portföyden 48'i.
    """
    with Session(seeded) as session:
        asset_ids = session.execute(select(Asset.id)).scalars().all()
        for asset_id in asset_ids:
            real_days = set(
                session.execute(
                    select(PriceHistory.price_date).where(
                        PriceHistory.asset_id == asset_id,
                        PriceHistory.source != PriceSource.SYNTHETIC,
                    )
                )
                .scalars()
                .all()
            )
            if not real_days:
                continue  # tamamen sentetik varlık (mevduat) — beklenen
            synthetic_days = (
                session.execute(
                    select(PriceHistory.price_date).where(
                        PriceHistory.asset_id == asset_id,
                        PriceHistory.source == PriceSource.SYNTHETIC,
                    )
                )
                .scalars()
                .all()
            )
            inside = [d for d in synthetic_days if min(real_days) <= d <= max(real_days)]
            symbol = session.execute(select(Asset.symbol).where(Asset.id == asset_id)).scalar_one()
            assert not inside, f"{symbol}: gerçek serinin içinde {len(inside)} sentetik gün"


def test_no_transaction_priced_from_synthetic_row(seeded):
    """Gerçek verisi olan bir varlıkta hiçbir işlem sentetik güne düşmemeli.

    I3'ün defter tarafındaki sonucu. Tamamen sentetik varlıklar (mevduat,
    ya da ağ olmadan koşan test ortamının tamamı) kapsam dışı: orada ölçek
    tutarlıdır, tehlike yalnızca KARIŞIMDA.
    """
    with Session(seeded) as session:
        assets_with_real = select(PriceHistory.asset_id).where(
            PriceHistory.source != PriceSource.SYNTHETIC
        )
        rows = session.execute(
            select(func.count())
            .select_from(Transaction)
            .join(
                PriceHistory,
                (PriceHistory.asset_id == Transaction.asset_id)
                & (PriceHistory.price_date == func.date(Transaction.transaction_date)),
            )
            .where(
                Transaction.asset_id.is_not(None),
                Transaction.asset_id.in_(assets_with_real),
                PriceHistory.source == PriceSource.SYNTHETIC,
            )
        ).scalar_one()
        assert rows == 0, f"{rows} işlem sentetik fiyatlı güne denk geliyor"


def test_synthetic_never_overwrites_real(seeded):
    with Session(seeded) as session:
        asset = session.execute(select(Asset).where(Asset.symbol == "THYAO")).scalar_one()
        day = settings.anchor_date

        upsert_prices(session, asset.id, [PricePoint(day, Decimal("111.111111"), PriceSource.TCMB)])
        upsert_prices(session, asset.id, [PricePoint(day, Decimal("1.0"), PriceSource.SYNTHETIC)])
        row = session.execute(
            select(PriceHistory).where(
                PriceHistory.asset_id == asset.id, PriceHistory.price_date == day
            )
        ).scalar_one()
        assert row.source == PriceSource.TCMB
        assert row.close_price == Decimal("111.111111")
        session.rollback()


# --------------------------------------------------------------------------
# I4 — her fiyat satırında kaynak + çekim zamanı (AK 5.3)
# --------------------------------------------------------------------------


def test_ak_5_3_price_source_and_timestamp(seeded):
    with Session(seeded) as session:
        missing = session.execute(
            select(func.count())
            .select_from(PriceHistory)
            .where((PriceHistory.source.is_(None)) | (PriceHistory.fetched_at.is_(None)))
        ).scalar_one()
        assert missing == 0


# --------------------------------------------------------------------------
# I5 — TRY dışı varlık, güncel kurla toplam değere girer (AK 5.7)
# --------------------------------------------------------------------------


def test_ak_5_7_fx_conversion(seeded):
    with Session(seeded) as session:
        user = User(email="fx@test.local", full_name="Test FX")
        session.add(user)
        session.flush()
        portfolio = Portfolio(user_id=user.id)
        session.add(portfolio)
        session.flush()

        # AKE = eurobond fonu, USD fiyatlanır. Evrende 21 ABD hissesi
        # eklendikten sonra tek TRY dışı varlık DEĞİL, ama dönüşümü izole
        # eden en sade örnek: tek varlıklı bir portföyde tutulup elde edilen
        # TRY değerinin `fiyat * kur` olduğu doğrudan doğrulanabiliyor.
        eurobond = session.execute(select(Asset).where(Asset.symbol == "AKE")).scalar_one()
        assert eurobond.currency == "USD"

        buy_day = _last_trading_day(session)
        bond_price_usd = _price_on(session, "AKE", buy_day)
        fx_at_buy = _price_on(session, "USDTRY", buy_day)

        record_transaction(
            session,
            portfolio.id,
            TransactionType.DEPOSIT,
            transaction_date=_tx_dt(buy_day),
            cash_amount_try=Decimal("1000000"),
        )
        record_transaction(
            session,
            portfolio.id,
            TransactionType.BUY,
            transaction_date=_tx_dt(buy_day),
            asset_id=eurobond.id,
            quantity=Decimal(10),
            price=bond_price_usd,
            currency="USD",
            fx_rate_to_try=fx_at_buy,  # işlem anındaki kur dondurulur
        )
        rebuild_holdings(session, portfolio.id)

        summary = get_portfolio_summary(session, user.id)
        latest_bond_usd = _latest_price(session, "AKE")
        latest_fx = _latest_price(session, "USDTRY")

        bond_alloc = next(
            item for item in summary.allocation if item.asset_class == AssetClass.BOND
        )
        expected = (Decimal(10) * latest_bond_usd * latest_fx).quantize(Decimal("0.01"))
        assert bond_alloc.value == expected, "USD varlık güncel kurla TRY'ye çevrilmeli"

        # unrealized_pnl de aynı kur mantığını kullanmalı (o günün kuru).
        pnl = unrealized_pnl(session, portfolio.id, as_of=buy_day)
        cost = Decimal(10) * bond_price_usd * fx_at_buy
        value_at_buy = Decimal(10) * bond_price_usd * fx_at_buy
        assert pnl == (value_at_buy - cost).quantize(Decimal("0.01"))
        session.rollback()


# --------------------------------------------------------------------------
# I6 — DEPOSIT/WITHDRAW getiri sayılmaz (FR-3, TWR)
# --------------------------------------------------------------------------


def test_external_flow_excluded_from_return(seeded):
    with Session(seeded) as session:
        user = User(email="twr@test.local", full_name="Test TWR")
        session.add(user)
        session.flush()
        portfolio = Portfolio(user_id=user.id)
        session.add(portfolio)
        session.flush()

        d_mid = _last_trading_day(session)
        d0 = d_mid - timedelta(days=14)

        record_transaction(
            session,
            portfolio.id,
            TransactionType.DEPOSIT,
            transaction_date=_tx_dt(d0),
            cash_amount_try=Decimal("100000"),
        )
        record_transaction(
            session,
            portfolio.id,
            TransactionType.DEPOSIT,
            transaction_date=_tx_dt(d_mid),
            cash_amount_try=Decimal("100000"),
        )

        # Varlık yok, fiyat hareketi yok: değer 100k -> 200k'ya yalnızca dış
        # akışla çıktı. Naif seri %100 getiri sanır; TWR %0 demeli.
        result = twr(session, portfolio.id, d0, d_mid)
        assert result == Decimal("0.00")
        session.rollback()


# --------------------------------------------------------------------------
# I7 — türetilmiş fiyat = kaynak × katsayı
# --------------------------------------------------------------------------


def test_derived_price_matches_factor(seeded):
    factor = SPEC_BY_SYMBOL["CEYREK"].derived_factor
    with Session(seeded) as session:
        xau_id = session.execute(select(Asset.id).where(Asset.symbol == "XAUTRY")).scalar_one()
        ceyrek_id = session.execute(select(Asset.id).where(Asset.symbol == "CEYREK")).scalar_one()

        xau = {
            d: p
            for d, p in session.execute(
                select(PriceHistory.price_date, PriceHistory.close_price).where(
                    PriceHistory.asset_id == xau_id
                )
            ).all()
        }
        ceyrek = session.execute(
            select(PriceHistory.price_date, PriceHistory.close_price).where(
                PriceHistory.asset_id == ceyrek_id
            )
        ).all()
        assert ceyrek, "türetilmiş varlığın fiyat serisi yok"
        for day, price in ceyrek:
            expected = (xau[day] * factor).quantize(Decimal("0.000001"))
            assert price == expected, f"{day}: {price} != {expected}"


# --------------------------------------------------------------------------
# Faktör modeli — sentetik varlıklar arası korelasyon sıfır olmamalı (AK-2.2/2.6)
# --------------------------------------------------------------------------


def _daily_returns(prices: list[Decimal]) -> list[float]:
    return [float(prices[i] / prices[i - 1]) - 1.0 for i in range(1, len(prices))]


def _correlation(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    mean_a, mean_b = sum(a) / n, sum(b) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b)) / n
    var_a = sum((x - mean_a) ** 2 for x in a) / n
    var_b = sum((y - mean_b) ** 2 for y in b) / n
    return cov / math.sqrt(var_a * var_b) if var_a and var_b else 0.0


def test_synthetic_correlation_nonzero(seeded):
    with Session(seeded) as session:

        def series(symbol: str) -> list[Decimal]:
            asset_id = session.execute(select(Asset.id).where(Asset.symbol == symbol)).scalar_one()
            return (
                session.execute(
                    select(PriceHistory.close_price)
                    .where(PriceHistory.asset_id == asset_id)
                    .order_by(PriceHistory.price_date)
                )
                .scalars()
                .all()
            )

        stock_pair = _correlation(_daily_returns(series("THYAO")), _daily_returns(series("GARAN")))
        fx_pair = _correlation(_daily_returns(series("USDTRY")), _daily_returns(series("EURTRY")))
        # Bağımsız random walk'larda bu değerler ~0 çıkıyordu (ölçülen -0.001).
        assert stock_pair > 0.35, f"hisse-hisse korelasyonu çok düşük: {stock_pair:.3f}"
        assert fx_pair > 0.6, f"döviz-döviz korelasyonu çok düşük: {fx_pair:.3f}"


# --------------------------------------------------------------------------
# I8 — Fon sınıflandırması: fonun ekonomik riski neyse sınıfı odur (AK 5.1)
# --------------------------------------------------------------------------


def test_fund_asset_class_follows_economic_risk():
    """Her TEFAS fonu, taşıdığı ekonomik riskin sınıfında olmalı.

    Beklenen tablo üretimdeki eşlemeden bağımsız yazılıdır; `_fund()` sınıfı
    `_FUND_ASSET_CLASS`'tan türettiği için o sözlüğü burada tekrar kullanmak
    kendini doğrulayan bir test olurdu.

    Regresyon koruması: tüm fonlar bir zamanlar AssetClass.STOCK idi. Altın
    fonu ve para piyasası fonu bu yüzden FR-4'ün "Hisse -> Yüksek" risk
    etiketini alıyor, risk motorunda savunma tarafında (BOND+CASH) sayılması
    gereken enstrüman hisse riski taşıyor görünüyordu.
    """
    expected = {
        "TI2": AssetClass.STOCK,  # hisse senedi fonu
        "TCD": AssetClass.STOCK,  # değişken fon
        "AFT": AssetClass.STOCK,  # teknoloji hisse fonu
        # Para piyasası fonu artık CASH DEĞİL: `AssetClass.CASH` yalnızca
        # serbest nakdi (defter bakiyesi) temsil ediyor. Bu bir yatırımdır,
        # fiyatı oynar (ölçülen %1,42 yıllık volatilite) ve kısa vadeli
        # borçlanma araçları tutar.
        "IOO": AssetClass.BOND,  # para piyasası fonu
        "GTA": AssetClass.PRECIOUS_METAL,  # altın fonu
        "AK2": AssetClass.BOND,  # uzun vadeli borçlanma araçları
        "APT": AssetClass.BOND,  # orta vadeli borçlanma araçları
        "AKE": AssetClass.BOND,  # eurobond
        "AYR": AssetClass.BOND,  # özel sektör borçlanma araçları
    }
    funds = {s.symbol: s for s in ASSET_UNIVERSE if s.data_source is PriceSource.TEFAS}
    assert set(funds) == set(expected), "TEFAS fon listesi değişti; beklenen tabloyu güncelleyin"
    for symbol, asset_class in expected.items():
        assert (
            funds[symbol].asset_class is asset_class
        ), f"{symbol}: {funds[symbol].asset_class.value} bekleniyordu {asset_class.value}"


def test_no_asset_is_synthetic():
    """HİÇBİR varlığın sentetik kaynağı olmamalı (AK 5.1).

    Eskiden mevduat (MEVDUAT-V / MEVDUAT-VS) kasıtlı istisnaydı: birim fiyatı
    sabit 1,00 TL olan, çekilecek piyasa fiyatı bulunmayan iki kayıt. Nakit
    artık bir VARLIK değil, defterdeki serbest bakiye olduğu için o istisnaya
    gerek kalmadı ve evren tamamen gerçek kaynaklı hâle geldi.

    Buraya yeni bir sembol düşerse o varlık sonsuza kadar bayat fiyatla
    değerlenir ve portföy özetinin as_of tarihi yanıltıcı olur.
    """
    synthetic = {s.symbol for s in ASSET_UNIVERSE if s.data_source is PriceSource.SYNTHETIC}
    assert synthetic == set(), f"sentetik kaynaklı varlık: {synthetic}"


def test_cash_class_has_no_assets():
    """`AssetClass.CASH` altında varlık OLMAMALI.

    Nakit yalnızca serbest bakiyedir (alım/satım için elde duran para) ve
    `portfolio_service` onu defterden okuyup dilime ekliyor. Buraya bir varlık
    düşerse nakit dilimi yine iki farklı şeyi karıştırmaya başlar — daha önce
    tam olarak bu oldu: mevduat, para piyasası fonu ve serbest bakiye aynı
    dilimde toplanıyor, portföyler olduğundan likit ve güvenli görünüyordu.
    """
    nakit = {s.symbol for s in ASSET_UNIVERSE if s.asset_class is AssetClass.CASH}
    assert nakit == set(), f"nakit sınıfında varlık var: {nakit}"


def test_fx_conversion_has_a_subject():
    """AK 5.7 kur dönüşümünü egzersiz eden en az bir TRY dışı varlık olmalı.

    test_ak_5_7_fx_conversion buna dayanır; evrenden çıkarsa o kod yolu
    seed'li evrende hiç çalışmaz ve testi sessizce anlamsızlaşır.
    """
    foreign = [s.symbol for s in ASSET_UNIVERSE if s.currency != "TRY"]
    assert foreign, "evrende TRY dışı varlık yok — AK 5.7 test edilemez"
