"""Portföy ile ilgili tüm SQL sorguları burada. API katmanı ve MCP tool'ları
bu modülü çağırır, kendileri sorgu yazmaz."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import AssetClass, AssetSubType, Granularity, TimeWindow, settings
from app.core.exceptions import InsufficientDataError, NotFoundError, ValidationAppError
from app.models import Asset, Holding, Portfolio, PriceHistory, Transaction, TransactionType
from app.schemas.portfolio import (
    AllocationItem,
    AssetClassReturn,
    BenchmarkComparison,
    BenchmarkEntry,
    GainLoss,
    HoldingRow,
    HoldingsValuation,
    PerformancePoint,
    PerformanceResult,
    PerformanceSummary,
    PerformerRef,
    PeriodChanges,
    PortfolioSummary,
    TransactionList,
    TransactionRow,
)
from app.services.ledger_service import (
    cash_balance_as_of,
    net_invested_as_of,
    position_as_of,
    total_deposits_as_of,
)
from app.services.price_service import bucket_last, resolve_granularity, window_start_date
from app.services.valuation_service import (
    FX_SYMBOL_BY_CURRENCY,
    PriceBook,
    realized_pnl,
    twr,
    unrealized_pnl,
    value_series,
)

_TWO_DECIMALS = Decimal("0.01")

# Kıyaslama endeksleri. XU100 evrende henüz tanımlı değil; varlık bulunamazsa
# sessizce atlanır, evrene eklendiği gün ek kod olmadan listeye girer.
# Arayüzdeki "Varlıklar Arası Karşılaştırmalı Getiri" kartının çubukları.
# Sıra kartta soldan sağa aynen korunur (bkz. `_benchmark_entries`).
#
# EURTRY 26 Ağustos 2026'da eklendi: kart beş enstrüman gösteriyor
# (portföy + BIST100 + USD + EUR + altın) ama uç yalnızca üçünü
# döndürüyordu, dolayısıyla euro çubuğu gerçek veriye bağlanamıyordu.
BENCHMARK_SYMBOLS = ("XU100", "USDTRY", "EURTRY", "XAUTRY")


def _round2(value: Decimal) -> Decimal:
    return value.quantize(_TWO_DECIMALS, rounding=ROUND_HALF_UP)


def _period_change(series: list[tuple[date, Decimal, Decimal]], days: int) -> Decimal | None:
    """`days` gün önceye göre yüzde değişim; dış akış etkisi ayrıştırılmış.

    ((son_değer − aradaki_dış_akış) / eski_değer − 1) × 100. Yeterli gün veya
    pozitif başlangıç sermayesi yoksa None döner — 0 yazmak "hiç değişmedi"
    demek olurdu ki bu bilgi elimizde yok.

    GÜN = TAKVİM GÜNÜ. Buraya gelen seri `value_series` çıktısıdır ve HER
    takvim gününü içerir (hafta sonları yalnızca GRAFİK noktalarından
    ayıklanır, bkz. `weekdays`). Dolayısıyla `days` kadar geri gitmek gerçekten
    `days` takvim günü geri gitmektir. Bu ayrım gözden kaçmaya çok müsait:
    döndürülen `series` alanı hafta sonlarını içermediği için, oraya bakıp
    "nokta sayıyor" sanmak kolay.
    """
    if len(series) <= days:
        return None
    base_value = series[-1 - days][1]
    if base_value <= 0:
        return None
    flows = sum((point[2] for point in series[-days:]), Decimal(0))
    return _round2(((series[-1][1] - flows) / base_value - 1) * 100)


# Fiyatı NOMİNAL olan enstrümanlar: birim değeri tanımı gereği 1 TL'dir ve
# değişmez. Getirileri fiyattan değil, deftere işlenen faiz hareketlerinden
# gelir (bkz. ledger_service).
_NOMINAL_PRICE_SUB_TYPES = frozenset(
    {AssetSubType.TIME_DEPOSIT.value, AssetSubType.DEMAND_DEPOSIT.value}
)


def _has_market_price(asset: Asset) -> bool:
    """Varlığın fiyatı bir PİYASADAN mı geliyor?

    Mevduatın fiyatı nominaldir; "eski fiyat" kavramının dışındadır —
    güncellenmediği için değil, güncellenecek bir şey olmadığı için.

    NEDEN `data_source` DEĞİL de `sub_type`: `data_source` varsayılanı
    `synthetic`, yani sağlayıcısı yazılmamış HER varlık sessizce "piyasa
    fiyatı yok" sayılırdı — gerçekten geride kalmış bir hisse de uyarı
    üretmezdi. `sub_type` tam olarak kastettiğimiz şeyi söylüyor.
    """
    return asset.sub_type not in _NOMINAL_PRICE_SUB_TYPES


def _latest_prices(db: Session, asset_ids: list[UUID]) -> dict[UUID, tuple[Decimal, date]]:
    """Verilen varlıklar için en güncel (en son tarihli) kapanış fiyatını döndürür."""
    if not asset_ids:
        return {}

    row_number = (
        func.row_number()
        .over(partition_by=PriceHistory.asset_id, order_by=PriceHistory.price_date.desc())
        .label("row_number")
    )
    subquery = (
        select(
            PriceHistory.asset_id,
            PriceHistory.close_price,
            PriceHistory.price_date,
            row_number,
        )
        .where(PriceHistory.asset_id.in_(asset_ids))
        .subquery()
    )
    rows = db.execute(
        select(subquery.c.asset_id, subquery.c.close_price, subquery.c.price_date).where(
            subquery.c.row_number == 1
        )
    ).all()
    return {row.asset_id: (row.close_price, row.price_date) for row in rows}


def _latest_fx_rates(db: Session, currencies: set[str]) -> dict[str, Decimal]:
    """TRY dışı para birimleri için en güncel kuru döndürür (1 birim kaç TRY).

    Kuru bulunamayan para birimi sözlükte HİÇ yer almaz; çağıran taraf bunu
    "değer hesaplanamaz" olarak yorumlar ve 0 ile doldurmaz (AK 5.5).
    """
    fx_symbols = {
        currency: FX_SYMBOL_BY_CURRENCY[currency]
        for currency in currencies
        if currency in FX_SYMBOL_BY_CURRENCY
    }
    if not fx_symbols:
        return {}

    fx_asset_rows = db.execute(
        select(Asset.id, Asset.symbol).where(Asset.symbol.in_(fx_symbols.values()))
    ).all()
    fx_prices = _latest_prices(db, [row.id for row in fx_asset_rows])
    symbol_to_price = {
        row.symbol: fx_prices[row.id][0] for row in fx_asset_rows if row.id in fx_prices
    }
    return {
        currency: symbol_to_price[symbol]
        for currency, symbol in fx_symbols.items()
        if symbol in symbol_to_price
    }


def get_portfolio_summary(db: Session, user_id: UUID) -> PortfolioSummary:
    portfolio = db.execute(
        select(Portfolio).where(Portfolio.user_id == user_id)
    ).scalar_one_or_none()
    if portfolio is None:
        raise NotFoundError(f"Portfolio not found for user_id {user_id}")

    holdings = (
        db.execute(
            select(Holding)
            .where(Holding.portfolio_id == portfolio.id)
            .options(joinedload(Holding.asset))
        )
        .scalars()
        .all()
    )

    latest_prices = _latest_prices(db, [h.asset_id for h in holdings])

    # AK 5.7: TRY dışı varlıklar güncel kurla dahil edilir. Kur varlıklarının
    # (USDTRY vb.) son kapanışı price_history'den okunur.
    fx_latest = _latest_fx_rates(
        db, {h.asset.currency for h in holdings if h.asset.currency != "TRY"}
    )

    total_value = Decimal(0)
    total_cost_basis = Decimal(0)
    class_values: dict[AssetClass, Decimal] = {}
    as_of_dates: list[date] = []
    # Yalnızca PİYASA fiyatı olan varlıkların tarihleri. Tazelik uyarısı buna
    # bakar; gerekçe aşağıda, `oldest_price_date` yanında.
    market_price_dates: list[date] = []

    for holding in holdings:
        price, price_date = latest_prices.get(holding.asset_id, (holding.avg_cost_price, None))
        if holding.asset.currency != "TRY":
            fx = fx_latest.get(holding.asset.currency)
            if fx is None:
                # Kur bilinmiyorsa değer uydurulmaz (AK 5.5); varlık toplam
                # değere maliyetiyle değil, hiç katılmaz — maliyet tarafı zaten
                # TRY cinsindendir ve aynen kalır.
                price = None
            else:
                price = price * fx
        market_value = holding.quantity * price if price is not None else Decimal(0)
        # avg_cost_price TRY cinsinden birim maliyettir (işlem anındaki kurla
        # dondurulmuş) — bkz. ledger_service maliyet sözleşmesi.
        cost_basis = holding.quantity * holding.avg_cost_price

        total_value += market_value
        total_cost_basis += cost_basis
        class_values[holding.asset.asset_class] = (
            class_values.get(holding.asset.asset_class, Decimal(0)) + market_value
        )
        if price_date is not None:
            as_of_dates.append(price_date)
            if _has_market_price(holding.asset):
                market_price_dates.append(price_date)

    # Serbest nakit (defterden): toplam değere ve 'cash' dilimine eklenir.
    cash_balance = cash_balance_as_of(db, portfolio.id)
    if cash_balance != 0:
        total_value += cash_balance
        class_values[AssetClass.CASH] = class_values.get(AssetClass.CASH, Decimal(0)) + cash_balance

    # Getirinin tabanı dışarıdan konan net sermayedir, holdings maliyeti DEĞİL.
    # total_cost_basis kullanıldığında serbest nakit değere giriyor ama tabana
    # girmiyordu; hesapta duran, hiç yatırıma dönüşmemiş para kâr olarak
    # raporlanıyordu (ölçüldü: 1.87M yatırmış bir portföyde 187.654 TL serbest
    # nakit, getiriyi %43,37 yerine %59,36 gösteriyordu).
    #
    # Bu tabanla `total_value - net_invested` özdeşliği korunur, yani ekrandaki
    # üç rakam birbirini tutar. Temettü/faiz dış akış olmadığı için kazanç
    # tarafında kalır — istenen davranış.
    net_invested = net_invested_as_of(db, portfolio.id)
    total_deposits = total_deposits_as_of(db, portfolio.id)

    # TUTAR ile ORAN farklı tabanlar kullanır ve bu kasıtlıdır.
    #
    # Tutar = değer - net sermaye. Çekim yapılmış portföyde de doğru sonucu
    # verir (1.000 yatır → 1.500 → 500 çek → değer 1.000; kazanç 500).
    #
    # Oran = tutar / TOPLAM YATIRILAN. Net sermaye payda olarak kullanılırsa
    # aynı örnekte %100 çıkar, oysa para %50 büyümüştür. Ayrıca toplam
    # yatırılan hiçbir zaman negatif olamaz; çekim yatırımı aşarsa net sermaye
    # negatife düşüyor ve oran anlamsızlaşıyordu.
    #
    # Defterden gelmeyen portföyde (holdings elle yazılmış, işlem kaydı yok)
    # her iki taban da 0'dır; o durumda varlık maliyetine düşülür.
    if total_deposits > 0:
        gain_amount = total_value - net_invested
        gain_percent = gain_amount / total_deposits * 100
    elif total_cost_basis > 0:
        gain_amount = total_value - total_cost_basis
        gain_percent = gain_amount / total_cost_basis * 100
    else:
        gain_amount = Decimal(0)
        gain_percent = Decimal(0)

    class_order = {asset_class: i for i, asset_class in enumerate(settings.supported_asset_classes)}
    allocation = [
        AllocationItem(
            asset_class=asset_class,
            value=_round2(value),
            percent=_round2(value / total_value * 100) if total_value > 0 else Decimal(0),
        )
        for asset_class, value in sorted(class_values.items(), key=lambda kv: class_order[kv[0]])
    ]

    return PortfolioSummary(
        user_id=user_id,
        as_of=max(as_of_dates) if as_of_dates else date.today(),
        # Özet, her varlığın KENDİ son fiyatıyla değerlenir; bu tarihler
        # birbirinden farklı olabilir. `as_of` en yenisini yazar, yani özet
        # olduğundan taze görünebilir. En eskisi de raporlanır ki sunum
        # katmanı ikisi ayrıştığında bunu söyleyebilsin (CLAUDE.md §4).
        #
        # PİYASA FİYATI OLMAYAN VARLIKLAR BU HESABA GİRMEZ. Mevduatın birim
        # fiyatı tanımı gereği 1 TL'dir ve hiç güncellenmez; son fiyat tarihi
        # seed'in çapasında donar. Hesaba katıldığında uyarı HER kullanıcıda,
        # kalıcı olarak çıkıyordu (ölçüldü: as_of 21.08 iken oldest 31.07) —
        # oysa mevduat "eskimiyor", sabit. Uyarının anlamlı kalması için
        # yalnızca gerçekten geride kalabilecek varlıklara bakılıyor.
        oldest_price_date=min(market_price_dates) if market_price_dates else None,
        total_value=_round2(total_value),
        total_cost_basis=_round2(total_cost_basis),
        net_invested=_round2(net_invested),
        total_gain_loss=GainLoss(amount=_round2(gain_amount), percent=_round2(gain_percent)),
        allocation=allocation,
        # Tamamen satılmış (quantity=0) satırlar gerçekleşmiş K-Z taşımak için
        # tabloda durur; aktif pozisyon sayısına katılmaz.
        holdings_count=sum(1 for h in holdings if h.quantity > 0),
    )


# ---------------------------------------------------------------------------
# Faz 2'de uygulanacak fonksiyonlar
#
# İmzalar ve dönüş şemaları sabittir: MCP tool'ları bunlara göre yazıldı ve
# ajanın planlayıcısı tool docstring'lerine göre seçim yapıyor. Gövdeler
# yazılana kadar @tool_handler NotImplementedError'ı INTERNAL_ERROR zarfına
# çevirir; sohbet çökmez, "alınamadı" der.
# ---------------------------------------------------------------------------


def get_held_asset_classes(db: Session, user_id: UUID) -> set[AssetClass]:
    """Kullanıcının GÜNCEL olarak (miktar > 0) elinde tuttuğu varlık
    sınıflarının kümesi.

    `get_holdings_valuation`'ın küçük bir alt kümesi gibi görünebilir ama
    BİLEREK ayrı ve daha ucuz: fiyat/değer hesabına hiç girmez, yalnızca
    "hangi SINIFLARDAN var" sorusuna cevap verir — Sinyal 5'in (profil_sapmasi,
    bkz. docs/notes/sinyal5-olay-tabanli-aktivasyon-tasarimi.md) ve
    `advice_eligibility`'nin girdisi SINIF SAHİPLİĞİDİR, değer değil.

    Tamamen satılmış (miktar 0) pozisyonlar sayılmaz. Fiyatı bulunamayan
    (`price_missing`) varlıklar İSE burada DIŞLANMAZ — sınıf sahipliği
    fiyatlanabilirlikten bağımsızdır (`get_holdings_valuation`'da
    `price_missing` yalnızca DEĞER alanlarını etkiler, bkz. o fonksiyonun
    docstring'i); fiyatı geçici olarak bulunamayan bir hisse hâlâ elde bir
    hissedir.

    Portföyü olmayan bir kullanıcı için boş küme döner, `NotFoundError`
    FIRLATMAZ — tek çağıranı (anket-olayı okuma) "elde hiçbir şey yok"
    durumunu geçerli, hata olmayan bir girdi olarak ele alıyor.
    """
    portfolio = db.execute(
        select(Portfolio).where(Portfolio.user_id == user_id)
    ).scalar_one_or_none()
    if portfolio is None:
        return set()

    holdings = (
        db.execute(
            select(Holding)
            .where(Holding.portfolio_id == portfolio.id, Holding.quantity > 0)
            .options(joinedload(Holding.asset))
        )
        .scalars()
        .all()
    )
    return {h.asset.asset_class for h in holdings}


def get_holdings_valuation(db: Session, user_id: UUID) -> HoldingsValuation:
    """Portföydeki varlıkları tek tek değerler.

    Maliyet: `Holding.avg_cost_price` zaten TRY birim maliyettir (işlem
    anındaki kurla çevrilmiş, alım komisyonu dahil, ağırlıklı ortalama — bkz.
    ledger_service maliyet sözleşmesi). Dolayısıyla
    `cost_basis_try = quantity * avg_cost_price`; defteri yeniden oynatmaya
    gerek yok.

    Güncel fiyat `_latest_prices` ile okunur; TRY dışı varlıklarda
    `get_portfolio_summary`'deki kur çevirimi kalıbı kullanılır. Kuru veya
    fiyatı bulunamayan varlık `price_missing=True` ile döner, değer alanları
    None kalır ve ağırlık hesabına girmez (AK-1.3, AK 5.5).

    `best_performer` / `worst_performer` `unrealized_pnl_percent`'e göre
    seçilir; fiyatı eksik varlıklar sıralamaya alınmaz. Bu değerler burada
    hesaplanır çünkü dil modelinin satırları karşılaştırıp en iyiyi bulması
    hesaplama sayılır ve yasaktır.

    quantity = 0 satırları (tamamen satılmış pozisyonlar) listeye dahil edilir:
    `realized_pnl_try` bilgisini taşırlar.

    AĞIRLIK PAYDASI: nakit DAHİL toplam portföy değeri — yani
    `get_portfolio_summary.total_value` ile aynı payda. Böylece buradaki varlık
    ağırlıkları pasta grafiğindeki sınıf ağırlıklarının içine tutarlı biçimde
    oturur. Sonuç: satırların ağırlıkları 100'e değil, (100 − nakit%) değerine
    toplanır. Nakit bir "holding" satırı olmadığı için burada listelenmez.

    Raises:
        NotFoundError: kullanıcının portföyü yok.
    """
    portfolio = db.execute(
        select(Portfolio).where(Portfolio.user_id == user_id)
    ).scalar_one_or_none()
    if portfolio is None:
        raise NotFoundError(f"Portfolio not found for user_id {user_id}")

    holdings = (
        db.execute(
            select(Holding)
            .where(Holding.portfolio_id == portfolio.id)
            .options(joinedload(Holding.asset))
        )
        .scalars()
        .all()
    )

    latest_prices = _latest_prices(db, [h.asset_id for h in holdings])
    fx_latest = _latest_fx_rates(
        db, {h.asset.currency for h in holdings if h.asset.currency != "TRY"}
    )

    # İki geçiş gerekiyor: ağırlığın paydası (toplam portföy değeri) ancak tüm
    # satırlar değerlendikten sonra biliniyor.
    ara_satirlar: list[dict] = []
    as_of_dates: list[date] = []
    excluded_symbols: list[str] = []
    total_market_value = Decimal(0)

    for holding in holdings:
        asset = holding.asset
        price, price_date = latest_prices.get(holding.asset_id, (None, None))

        # TRY dışı varlık: O GÜNÜN değil, en güncel kurla çevrilir — bu
        # fonksiyon "şu an ne kadar eder" sorusunu cevaplıyor.
        if price is not None and asset.currency != "TRY":
            fx = fx_latest.get(asset.currency)
            price = None if fx is None else price * fx

        # avg_cost_price TRY birim maliyettir (işlem anındaki kurla dondurulmuş,
        # komisyon dahil) — bkz. ledger_service maliyet sözleşmesi.
        cost_basis = _round2(holding.quantity * holding.avg_cost_price)

        if price is None:
            # Fiyat veya kur yok: satır düşmez ama değer alanları None kalır.
            excluded_symbols.append(asset.symbol)
            market_value = None
            price_try = None
            unrealized = None
            unrealized_percent = None
        else:
            price_try = _round2(price)
            market_value = _round2(holding.quantity * price)
            total_market_value += market_value
            unrealized = _round2(market_value - cost_basis)
            # Maliyeti sıfır olan satırda yüzde tanımsız (tamamen satılmış
            # pozisyon ya da bedelsiz giriş); 0 yazmak yanlış olurdu.
            unrealized_percent = _round2(unrealized / cost_basis * 100) if cost_basis > 0 else None
            if price_date is not None:
                as_of_dates.append(price_date)

        ara_satirlar.append(
            {
                "symbol": asset.symbol,
                "name": asset.name,
                "asset_class": asset.asset_class,
                "currency": asset.currency,
                "quantity": holding.quantity,
                "current_price_try": price_try,
                "market_value_try": market_value,
                "avg_cost_try": holding.avg_cost_price,
                "cost_basis_try": cost_basis,
                "unrealized_pnl_try": unrealized,
                "unrealized_pnl_percent": unrealized_percent,
                "realized_pnl_try": _round2(holding.realized_pnl_try),
                "price_missing": price is None,
            }
        )

    # Payda get_portfolio_summary ile aynı olmalı: serbest nakit de dahil.
    total_portfolio_value = total_market_value + cash_balance_as_of(db, portfolio.id)

    # Tablo okunabilirliği: büyükten küçüğe, fiyatı bilinmeyenler en sonda.
    ara_satirlar.sort(
        key=lambda r: (r["market_value_try"] is None, -(r["market_value_try"] or Decimal(0)))
    )

    rows = [
        HoldingRow(
            **satir,
            weight_percent=(
                _round2(satir["market_value_try"] / total_portfolio_value * 100)
                if satir["market_value_try"] is not None and total_portfolio_value > 0
                else None
            ),
        )
        for satir in ara_satirlar
    ]

    # En iyi/en kötü: yüzdesi hesaplanabilen AÇIK pozisyonlar arasından.
    # Kapanmış (quantity=0) satırın güncel getirisi yoktur, sıralamaya girmez.
    ranked = [r for r in rows if r.unrealized_pnl_percent is not None and r.quantity > 0]

    def _performer(row: HoldingRow) -> PerformerRef:
        return PerformerRef(
            symbol=row.symbol,
            name=row.name,
            unrealized_pnl_percent=row.unrealized_pnl_percent,
        )

    return HoldingsValuation(
        user_id=user_id,
        as_of=max(as_of_dates) if as_of_dates else date.today(),
        holdings=rows,
        best_performer=(
            _performer(max(ranked, key=lambda r: r.unrealized_pnl_percent)) if ranked else None
        ),
        worst_performer=(
            _performer(min(ranked, key=lambda r: r.unrealized_pnl_percent)) if ranked else None
        ),
        excluded_symbols=excluded_symbols,
    )


def get_portfolio_performance(db: Session, user_id: UUID, window: TimeWindow) -> PerformanceResult:
    """Portföyün değer serisini ve dönemsel değişimini üretir.

    `valuation_service.value_series` sarmalanır: o fonksiyon (gün, toplam
    değer, dış akış) üçlüsü döndürüyor. Buradaki iş üç adım:

    1. Dış akışı kümülatife çevir → `invested_try`. Yalnızca DEPOSIT/WITHDRAW
       sayılır (value_series zaten öyle yapıyor); BUY/SELL yeni para değildir,
       sayılırsa sat-yeniden al yapan kullanıcıda tutar şişer.
    2. Seriyi hedef nokta sayısına indir (~60-120). Her kovanın SON işlem günü
       değeri alınır, ortalama ALINMAZ — ortalama hiç var olmamış bir değer
       üretir. Hafta sonları seriye girmez.
    3. Özet skalerleri hesapla. `changes.daily/weekly/monthly` için yeterli
       veri yoksa None döner, 0 değil.

    `start = max(inception, as_of - window)`; pencere portföyün ömründen
    uzunsa `truncated_to_inception=True`. İlk işlemden önce dolgu yapılmaz —
    portföy yokken değeri 0 göstermek uydurma veridir.

    ÖZET ÇİFTİ: `change_amount` ile `change_percent` birlikte okunmalı ve
    ikisi de dış akıştan ARINDIRILMIŞTIR:

    - `change_amount` = (son değer − ilk değer) − dönem içi net para giriş/çıkışı
    - `change_percent` = TWR (zaman ağırlıklı getiri)

    Ham değer farkı kullanılsaydı, para yatıran kullanıcı hiçbir şey kazanmadan
    "kâr ettim" görürdü. Grafikteki `value_try` ↔ `invested_try` boşluğu ise
    ham hâliyle duruyor; kullanıcı toplam kârı oradan görüyor.

    Raises:
        NotFoundError: portföy yok.
        InsufficientDataError: portföyde hiç işlem yok ya da pencerede veri yok.
    """
    portfolio = db.execute(
        select(Portfolio).where(Portfolio.user_id == user_id)
    ).scalar_one_or_none()
    if portfolio is None:
        raise NotFoundError(f"Portfolio not found for user_id {user_id}")

    inception_dt = db.execute(
        select(func.min(Transaction.transaction_date)).where(
            Transaction.portfolio_id == portfolio.id
        )
    ).scalar()
    if inception_dt is None:
        raise InsufficientDataError(f"No transactions for portfolio {portfolio.id}")
    inception = inception_dt.date()

    # Seri son FİYAT gününde biter, bugünde değil: fiyat hattı geride kalmışsa
    # (daily_update çalışmamışsa) bugüne kadar uzatmak, son bilinen fiyatı
    # tekrar tekrar çizip "değer değişmedi" yanılsaması üretirdi.
    portfolio_asset_ids = (
        db.execute(
            select(Transaction.asset_id)
            .where(
                Transaction.portfolio_id == portfolio.id,
                Transaction.asset_id.is_not(None),
            )
            .distinct()
        )
        .scalars()
        .all()
    )
    last_price_date = db.execute(
        select(func.max(PriceHistory.price_date)).where(
            PriceHistory.asset_id.in_(portfolio_asset_ids)
        )
    ).scalar()
    as_of = last_price_date or date.today()
    # Seri portföyün DOĞUMUNDAN önce bitemez.
    #
    # Fiyat hattı günlük iş akşam koştuğu için gün içinde bir gün geride
    # olabiliyor. Bugün açılan bir hesap bugün alım yaptığında `inception`
    # bugün, `last_price_date` dün oluyordu; `start = max(inception, ...)`
    # bugüne, `as_of` düne düşüyor ve aşağıdaki `start > as_of` kontrolü
    # `InsufficientDataError` fırlatıyordu. Sonuç: yeni kullanıcı ilk alımını
    # yapar yapmaz Dashboard'u kaybediyordu (ölçüldü, 28 Ağustos 2026).
    #
    # `as_of`ı bugüne kadar UZATMIYORUZ — o, son bilinen fiyatı tekrar tekrar
    # çizip "değer değişmedi" yanılsaması üretirdi (yukarıdaki not). Yalnızca
    # `inception`a çekiliyor: portföyün var olduğu ilk gün seride yer almak
    # zorunda ve o gün, özet ekranıyla aynı biçimde son kapanışla değerlenir.
    as_of = max(as_of, inception)

    window_start = window_start_date(window, as_of)
    start = max(inception, window_start)
    truncated = inception > window_start
    if start > as_of:
        raise InsufficientDataError(
            f"No data in window for portfolio {portfolio.id} ({start} > {as_of})"
        )

    series = value_series(db, portfolio.id, start, as_of)
    if not series:
        raise InsufficientDataError(f"Empty value series for portfolio {portfolio.id}")

    # Kümülatif yatırılan para pencerenin başında sıfırlanmaz: grafikteki
    # "değer ↔ yatırılan" boşluğu ancak portföyün başından beri sayıldığında
    # toplam kârı gösterir.
    flow_before_start = db.execute(
        select(func.coalesce(func.sum(Transaction.cash_amount_try), 0)).where(
            Transaction.portfolio_id == portfolio.id,
            Transaction.transaction_type.in_([TransactionType.DEPOSIT, TransactionType.WITHDRAW]),
            func.date(Transaction.transaction_date) < start,
        )
    ).scalar() or Decimal(0)

    cumulative: dict[date, Decimal] = {}
    running = Decimal(flow_before_start)
    for day, _value, flow in series:
        running += flow
        cumulative[day] = running

    # Hafta sonları düşer: borsa kapalı, fiyat taşındığı için o günler grafikte
    # yatay tekrar üretir. Akış birikimi yukarıda TÜM günler üzerinden
    # yapıldığı için hafta sonu yatırılan para kaybolmaz.
    weekdays = [point for point in series if point[0].weekday() < 5]
    if not weekdays:
        weekdays = series

    granularity = resolve_granularity(window, Granularity.AUTO)
    points = [
        PerformancePoint(date=day, value_try=value, invested_try=cumulative[day])
        for day, value, _flow in bucket_last(weekdays, granularity)
    ]

    start_value = series[0][1]
    end_value = series[-1][1]
    # İlk günün akışı başlangıç sermayesidir, dönem içi giriş sayılmaz.
    net_flow = sum((point[2] for point in series[1:]), Decimal(0))

    summary = PerformanceSummary(
        start_value=start_value,
        end_value=end_value,
        change_amount=_round2(end_value - start_value - net_flow),
        change_percent=twr(db, portfolio.id, start, as_of),
        realized_pnl=realized_pnl(db, portfolio.id, start, as_of),
        unrealized_pnl=unrealized_pnl(db, portfolio.id, as_of),
        changes=PeriodChanges(
            # `series` (ham) kullanılıyor, `points` (hafta sonu ayıklanmış)
            # değil: dönemler takvim günü cinsindendir. Hafta sonunda değer
            # Cuma kapanışıyla taşındığı için Pazartesi bakan kullanıcı
            # Cuma→Pazartesi değişimini görür — istenen davranış budur.
            daily=_period_change(series, 1),
            weekly=_period_change(series, 7),
            monthly=_period_change(series, 30),
        ),
    )

    return PerformanceResult(
        user_id=user_id,
        as_of=as_of,
        window=window,
        granularity=granularity,
        inception=inception,
        truncated_to_inception=truncated,
        series=points,
        summary=summary,
    )


def get_transactions(
    db: Session,
    user_id: UUID,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    symbols: list[str] | None = None,
    asset_class: AssetClass | None = None,
) -> TransactionList:
    """İşlem defterini filtreleyerek döndürür.

    `position_after` defterin tarih sırasıyla oynatılmasıyla üretilir:
    grafikteki alım işaretçisinin hover detayında "bu işlemden sonra elimde ne
    kaldı" bilgisi için. Filtre uygulansa bile pozisyon defterin başından
    itibaren sayılmalıdır, yoksa değer yanlış çıkar.

    `symbols` verilmezse nakit hareketleri (DEPOSIT/WITHDRAW/FEE/INTEREST) de
    listeye girer; verilirse yalnızca o sembollere ait BUY/SELL/DIVIDEND döner.

    `asset_class` "hangi HİSSELERİ aldım" gibi sınıf bazlı sorular içindir.
    Sembol süzgeciyle aynı şeyi yapamaz: çağıran taraf (ajanın planlayıcısı)
    kullanıcının hangi sembollerinin hisse olduğunu bilmiyor. Süzgeç yokken
    "Temmuz'da hangi hisseleri aldım?" sorusuna bir TAHVİL fonu dönüyordu
    (ölçüldü, 23 Ağustos test turu). Sınıf süzgeci de sembol süzgeci gibi
    nakit hareketlerini listeden çıkarır.

    SIRALAMA: eskiden yeniye. Grafikteki işaretçiler zaman ekseninde soldan
    sağa diziliyor; `position_after` da ancak bu sırada anlamlı.

    Raises:
        NotFoundError: portföy yok.
        ValidationAppError: start_date > end_date.
    """
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValidationAppError(f"start_date {start_date} is after end_date {end_date}")

    portfolio = db.execute(
        select(Portfolio).where(Portfolio.user_id == user_id)
    ).scalar_one_or_none()
    if portfolio is None:
        raise NotFoundError(f"Portfolio not found for user_id {user_id}")

    # Defterin TAMAMI okunur, filtre sonradan uygulanır: `position_after`
    # "bu işlemden sonra elimde ne kaldı" demek ve bu ancak baştan sayılarak
    # bulunur. Yalnızca filtrelenmiş aralık oynatılsaydı, pencere öncesindeki
    # alımlar sayılmaz ve pozisyon olduğundan küçük çıkardı.
    transactions = (
        db.execute(
            select(Transaction)
            .where(Transaction.portfolio_id == portfolio.id)
            .options(joinedload(Transaction.asset))
            .order_by(Transaction.transaction_date, Transaction.created_at)
        )
        .scalars()
        .all()
    )

    wanted_symbols = {s.strip().upper() for s in symbols} if symbols else None

    running: dict[UUID, Decimal] = {}
    rows: list[TransactionRow] = []

    for tx in transactions:
        # Pozisyon her işlemde güncellenir — satır filtreye takılsa bile,
        # yoksa sayaç bozulur.
        position_after: Decimal | None = None
        if tx.asset_id is not None:
            quantity = running.get(tx.asset_id, Decimal(0))
            if tx.transaction_type == TransactionType.BUY:
                quantity += tx.quantity
            elif tx.transaction_type == TransactionType.SELL:
                quantity -= tx.quantity
            # DIVIDEND miktarı değiştirmez, yalnızca nakit getirir.
            running[tx.asset_id] = quantity
            position_after = quantity

        tx_date = tx.transaction_date.date()
        if start_date is not None and tx_date < start_date:
            continue
        if end_date is not None and tx_date > end_date:
            continue

        symbol = tx.asset.symbol if tx.asset is not None else None
        if asset_class is not None and (
            tx.asset is None or tx.asset.asset_class is not asset_class
        ):
            continue
        if wanted_symbols is not None:
            # Sembol süzgeci verildiğinde nakit hareketleri (DEPOSIT/WITHDRAW/
            # FEE/INTEREST) listeye girmez: "TUPRS'ta ne yaptım" sorusunun
            # cevabında maaş yatırma kaydının işi yok.
            if symbol is None or symbol not in wanted_symbols:
                continue

        rows.append(
            TransactionRow(
                transaction_date=tx.transaction_date,
                type=tx.transaction_type,
                symbol=symbol,
                quantity=tx.quantity,
                price=tx.price,
                currency=tx.currency,
                fx_rate_to_try=tx.fx_rate_to_try,
                fee_try=_round2(tx.fee_try),
                cash_amount_try=_round2(tx.cash_amount_try),
                position_after=position_after,
            )
        )

    return TransactionList(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        transactions=rows,
    )


def get_benchmark_comparison(db: Session, user_id: UUID, window: TimeWindow) -> BenchmarkComparison:
    """Portföyün dönem getirisini endekslerle karşılaştırır.

    PORTFÖY ÇUBUĞU, PERFORMANS KARTIYLA AYNI SAYIYI VERİR. İkisi de
    `valuation_service.twr` çağırır ve pencereyi birebir aynı kurar:
    `inception` = ilk işlem (nakit yatırma dahil), `end_date` = portföyün
    varlıklarındaki son fiyat günü, `start = max(inception, pencere başı)`.
    Aynı girdi + aynı fonksiyon = aynı sayı; iki kartın birbirini tutması
    için ayrı ayrı doğru olmalarına güvenmek gerekmiyor.

    NEDEN DEĞİŞTİ (31 Ağustos 2026). Çubuk daha önce t0 miktarlarını
    dondurup yalnızca fiyat değişimini ölçüyordu:

        C = Σ qᵢ(t0) × pᵢ(t0)   V = Σ qᵢ(t0) × pᵢ(t1)   getiri = V/C − 1

    Ölçüldü (seed'li 12 kullanıcı, 12 aylık pencere): nakdi %79 olan
    kullanıcıda çubuk +%44,54 derken performans kartı +%4,46 diyordu; iki
    kullanıcıda İŞARET ters dönüyordu (çubuk −%5,95, kart +%0,92). Yani aynı
    sayfada bir kart "kârdasın", diğeri "zarardasın" diyordu. İki sebebi
    vardı:

    1. **Nakit çubuğa hiç girmiyordu.** Nakit bir pozisyon değil, defter
       bakiyesi; `position_as_of` onu döndürmez. Diğer bütün kartlar (özet,
       performans) nakit dahil tüm portföyü değerliyor. En büyük iki sapma,
       en nakit ağırlıklı iki portföydü — tesadüf değil.
    2. **Dönem içi alım/satım yok sayılıyordu.** t0 sepeti donduğu için mart
       ayında satılan zararlı varlık ağustosta hâlâ portföydeymiş gibi
       ölçülüyordu.

    Kartın cevapladığı soru "bu dönemde param mı, BIST mi daha çok
    kazandırdı" olduğuna göre doğru portföy ölçüsü TWR'dir: dış para
    giriş-çıkışından arındırılmış, nakit dahil gerçek getiri.

    ÖLÇEK FARKI BİLİNÇLİDİR. Portföy çubuğu nakit dahil gerçek getiri,
    endeksler saf fiyat getirisi: 100 × (p(t1)/p(t0) − 1). Hesapta duran para
    getiri üretmez, endeks ise tamamen yatırımdadır — bu bir hesap hatası
    değil, kullanıcının gerçekten yaşadığı fark. Arayüzde açıkça yazılıyor.

    `by_asset_class` DONMUŞ t0 sepetinin sınıf bazlı FİYAT getirisidir;
    headline ile aynı ölçü DEĞİLDİR ve toplamı ona eşit çıkmaz. "Hangi sınıf
    ne kadar oynadı" sorusunu cevaplar. Arayüzde henüz gösterilmiyor.

    `excluded_symbols` dönem sonunda fiyatı bulunamayan, bu yüzden portföy
    değerine hiç girmeyen sembollerdir (AK 5.5: eksik veri tamamlanmaz,
    bildirilir).

    Raises:
        NotFoundError: portföy yok.
        InsufficientDataError: portföyde hiç işlem yok.
    """
    portfolio = db.execute(
        select(Portfolio).where(Portfolio.user_id == user_id)
    ).scalar_one_or_none()
    if portfolio is None:
        raise NotFoundError(f"Portfolio not found for user_id {user_id}")

    # PENCERE `get_portfolio_performance` İLE AYNI KURULUR — aşağıdaki blok
    # oradakinin aynısıdır. Ayrışırlarsa iki kart yine farklı sayı gösterir;
    # `tests/test_portfolio_service_faz2.py` bunu kilitliyor.
    #
    # `inception` ilk VARLIK ALIMI değil, İLK İŞLEMDİR (nakit yatırma dahil):
    # TWR nakit üzerinde de tanımlıdır (getirisi sıfırdır), dolayısıyla fiyat
    # getirisinin aksine "hiçbir şeye sahip olmadığın gün" sorunu yok.
    inception_dt = db.execute(
        select(func.min(Transaction.transaction_date)).where(
            Transaction.portfolio_id == portfolio.id
        )
    ).scalar()
    if inception_dt is None:
        raise InsufficientDataError(f"No transactions for portfolio {portfolio.id}")
    inception = inception_dt.date()

    portfolio_asset_ids = (
        db.execute(
            select(Transaction.asset_id)
            .where(
                Transaction.portfolio_id == portfolio.id,
                Transaction.asset_id.is_not(None),
            )
            .distinct()
        )
        .scalars()
        .all()
    )
    last_price_date = db.execute(
        select(func.max(PriceHistory.price_date)).where(
            PriceHistory.asset_id.in_(portfolio_asset_ids)
        )
    ).scalar()
    end_date = max(last_price_date or date.today(), inception)

    window_start = window_start_date(window, end_date)
    start_date = max(inception, window_start)
    truncated = inception > window_start

    # Portföy çubuğu: performans kartındaki `summary.change_percent` ile AYNI
    # çağrı. Hesaplanamıyorsa (pencerede hiç sermaye yoksa) None döner, hata
    # fırlatılmaz — endeks çubukları hesaplanabiliyorken tüm kartı karartmak
    # "veri yok" gibi okunurdu (zarif düşüş).
    portfolio_return = twr(db, portfolio.id, start_date, end_date)

    positions_start = position_as_of(db, portfolio.id, start_date)
    positions_end = position_as_of(db, portfolio.id, end_date)

    benchmark_assets = (
        db.execute(select(Asset).where(Asset.symbol.in_(BENCHMARK_SYMBOLS))).scalars().all()
    )
    position_ids = set(positions_start) | set(positions_end)
    position_assets = (
        db.execute(select(Asset).where(Asset.id.in_(list(position_ids)))).scalars().all()
        if position_ids
        else []
    )

    # Kur varlıkları da fiyat defterine girmeli: TRY dışı varlık O GÜNÜN
    # kuruyla çevrilir, bugünkü kurla değil.
    currencies = {a.currency for a in position_assets if a.currency != "TRY"}
    fx_rows = db.execute(
        select(Asset.id, Asset.symbol).where(
            Asset.symbol.in_(
                [FX_SYMBOL_BY_CURRENCY[c] for c in currencies if c in FX_SYMBOL_BY_CURRENCY]
            )
        )
    ).all()
    fx_id_by_symbol = {symbol: asset_id for asset_id, symbol in fx_rows}
    fx_id_by_currency = {
        currency: fx_id_by_symbol[FX_SYMBOL_BY_CURRENCY[currency]]
        for currency in currencies
        if FX_SYMBOL_BY_CURRENCY.get(currency) in fx_id_by_symbol
    }

    book_asset_ids = (
        position_ids | {a.id for a in benchmark_assets} | set(fx_id_by_currency.values())
    )
    price_rows = (
        db.execute(
            select(PriceHistory.asset_id, PriceHistory.price_date, PriceHistory.close_price).where(
                PriceHistory.asset_id.in_(list(book_asset_ids))
            )
        ).all()
        if book_asset_ids
        else []
    )
    book = PriceBook([(r.asset_id, r.price_date, r.close_price) for r in price_rows])

    currency_by_asset = {a.id: a.currency for a in position_assets}

    def _price_try(asset_id: UUID, day: date) -> Decimal | None:
        """Varlığın o günkü TRY fiyatı. Kur veya fiyat yoksa None — eksik veri
        tamamlanmaz (AK 5.5)."""
        price = book.price_at(asset_id, day)
        if price is None:
            return None
        currency = currency_by_asset.get(asset_id, "TRY")
        if currency == "TRY":
            return price
        fx_asset_id = fx_id_by_currency.get(currency)
        if fx_asset_id is None:
            return None
        fx = book.price_at(fx_asset_id, day)
        return None if fx is None else price * fx

    asset_by_id = {a.id: a for a in position_assets}

    # Dönem SONUNDA elde olup fiyatlanamayan varlıklar: değer serisine 0
    # katkı verirler, dolayısıyla portföy getirisi eksik hesaplanmıştır.
    # Sessiz kalmak, olmayan bir tamlık iddiasıdır.
    excluded_symbols = sorted(
        asset_by_id[asset_id].symbol
        for asset_id in positions_end
        if asset_id in asset_by_id and _price_try(asset_id, end_date) is None
    )

    # Sınıf kırılımı: donmuş t0 sepetinin FİYAT getirisi (headline'dan farklı
    # ölçü — bkz. docstring). ΣV/ΣC zaten ağırlıklı ortalamadır.
    by_class: dict[AssetClass, list[Decimal]] = {}
    for asset_id, quantity in positions_start.items():
        asset = asset_by_id.get(asset_id)
        if asset is None:
            continue
        price_start = _price_try(asset_id, start_date)
        price_end = _price_try(asset_id, end_date)
        if price_start is None or price_end is None or price_start <= 0:
            continue
        bucket = by_class.setdefault(asset.asset_class, [Decimal(0), Decimal(0)])
        bucket[0] += quantity * price_start
        bucket[1] += quantity * price_end

    def _return_percent(cost: Decimal, value: Decimal) -> Decimal | None:
        return _round2((value / cost - 1) * 100) if cost > 0 else None

    class_order = {asset_class: i for i, asset_class in enumerate(settings.supported_asset_classes)}
    by_asset_class = [
        AssetClassReturn(asset_class=asset_class, return_percent=_return_percent(*sums))
        for asset_class, sums in sorted(by_class.items(), key=lambda kv: class_order[kv[0]])
    ]

    # Endeksler aynı pencerede saf fiyat getirisi: 100 × (p(t1)/p(t0) − 1).
    # Sıra BENCHMARK_SYMBOLS'e sadık kalır ki arayüzdeki bar grafiği her
    # çağrıda aynı düzende çizilsin.
    benchmark_by_symbol = {a.symbol: a for a in benchmark_assets}
    benchmarks: list[BenchmarkEntry] = []
    for symbol in BENCHMARK_SYMBOLS:
        asset = benchmark_by_symbol.get(symbol)
        if asset is None:
            continue
        price_start = book.price_at(asset.id, start_date)
        price_end = book.price_at(asset.id, end_date)
        benchmarks.append(
            BenchmarkEntry(
                symbol=asset.symbol,
                name=asset.name,
                return_percent=(
                    _round2((price_end / price_start - 1) * 100)
                    if price_start and price_end and price_start > 0
                    else None
                ),
            )
        )

    return BenchmarkComparison(
        user_id=user_id,
        window=window,
        start_date=start_date,
        end_date=end_date,
        truncated_to_inception=truncated,
        portfolio_return_percent=portfolio_return,
        by_asset_class=by_asset_class,
        benchmarks=benchmarks,
        excluded_symbols=excluded_symbols,
    )
