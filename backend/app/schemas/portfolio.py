"""Portföy API'sinin ekip sözleşmesi. Frontend'deki src/types/ altındaki
TypeScript tipleri bu şemayla eşleşmelidir.

Bu modeller aynı zamanda MCP tool'larının çıktı şeklidir: tool gövdeleri
`model_dump(mode="json")` ile döndürür, `@tool_handler` zarfı kurar
(bkz. docs/MCP-TOOLS.md).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, PlainSerializer

from app.core.config import AssetClass, Granularity, PriceCurrency, TimeWindow
from app.models.transaction import TransactionType

# Hesaplamalarda hassasiyet kaybını önlemek için Decimal kullanılır, ama JSON'a
# giderken düz sayı (float) olarak serialize edilir — string değil, ki frontend
# doğrudan number olarak tüketebilsin.
Money = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]

# Hesaplanamayan değer için. Eksik veriyi 0 ile doldurmak sessizce yanlış sayı
# üretmek olurdu (AK 5.5, "uydurma yok"); None döner, sunum katmanı "—" gösterir.
MoneyOpt = Annotated[
    Decimal | None,
    PlainSerializer(
        lambda v: None if v is None else float(v),
        return_type=float | None,
        when_used="json",
    ),
]


class GainLoss(BaseModel):
    model_config = ConfigDict(frozen=True)

    amount: Money
    percent: Money


class AllocationItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    asset_class: AssetClass
    value: Money
    percent: Money


class PortfolioSummary(BaseModel):
    """Portföy özeti.

    İki farklı taban vardır, karıştırılmamalı:

    - `total_cost_basis`: yalnızca ELDE TUTULAN varlıkların maliyeti. Serbest
      nakit içermez, çünkü nakit satın alınmış bir varlık değildir.
    - `net_invested`: dışarıdan konan net sermaye (yatırma − çekme). Serbest
      nakit de bunun içindedir.

    `total_gain_loss` **`net_invested`'a göre** hesaplanır ve
    `total_value - net_invested`'a eşittir; böylece ekrandaki üç rakam
    birbirini tutar. `total_cost_basis` kullanılsaydı hesapta duran, hiç
    yatırıma dönüşmemiş para kâr sayılırdı.
    """

    model_config = ConfigDict(frozen=True)

    user_id: UUID
    as_of: date
    total_value: Money
    total_cost_basis: Money
    net_invested: Money
    total_gain_loss: GainLoss
    allocation: list[AllocationItem]
    holdings_count: int


# ---------------------------------------------------------------------------
# get_holdings
# ---------------------------------------------------------------------------


class HoldingRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    asset_class: AssetClass
    currency: str
    quantity: Money
    # Fiyatı bulunamayan varlıkta bunlar None ve `price_missing` True olur;
    # satır yine döner ki kullanıcı varlığın var olduğunu görsün (AK-1.3).
    current_price_try: MoneyOpt = None
    market_value_try: MoneyOpt = None
    weight_percent: MoneyOpt = None
    # Birim ve toplam maliyet, işlem anındaki kurla ve komisyon dahil
    # (bkz. ledger_service maliyet sözleşmesi).
    avg_cost_try: Money
    cost_basis_try: Money
    unrealized_pnl_try: MoneyOpt = None
    unrealized_pnl_percent: MoneyOpt = None
    realized_pnl_try: Money
    price_missing: bool = False


class PerformerRef(BaseModel):
    """En iyi / en kötü performans gösteren varlık.

    Türetilmiş değer olduğu için burada hazır veriliyor: dil modelinin iki
    satırı karşılaştırıp "en çok kazandıran bu" demesi hesaplama sayılır ve
    yasaktır.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    unrealized_pnl_percent: Money


class HoldingsValuation(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    as_of: date
    holdings: list[HoldingRow]
    # Fiyatı eksik varlıklar sıralamaya girmez.
    best_performer: PerformerRef | None = None
    worst_performer: PerformerRef | None = None
    excluded_symbols: list[str] = []


# ---------------------------------------------------------------------------
# get_portfolio_performance
# ---------------------------------------------------------------------------


class PerformancePoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: date
    value_try: Money
    # Kümülatif dış akış (yatırılan − çekilen). Değerle arasındaki fark
    # toplam kârdır; ikinci bir hesap gerekmez.
    invested_try: Money


class PeriodChanges(BaseModel):
    """Dönemsel değişim yüzdeleri (FR-3). Yeterli veri yoksa None — 0 değil."""

    model_config = ConfigDict(frozen=True)

    daily: MoneyOpt = None
    weekly: MoneyOpt = None
    monthly: MoneyOpt = None


class PerformanceSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    start_value: Money
    end_value: Money
    change_amount: Money
    change_percent: MoneyOpt = None
    realized_pnl: Money
    unrealized_pnl: Money
    changes: PeriodChanges


class PerformanceResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    as_of: date
    window: TimeWindow
    granularity: Granularity
    inception: date
    # Pencere portföyün ömründen uzunsa başlangıç ilk işleme kırpıldı demektir;
    # arayüz "portföy başlangıcı" etiketi gösterir, sahte düz çizgi çizmez.
    truncated_to_inception: bool = False
    series: list[PerformancePoint]
    summary: PerformanceSummary


# ---------------------------------------------------------------------------
# get_transactions
# ---------------------------------------------------------------------------


class TransactionRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    transaction_date: datetime
    type: TransactionType
    symbol: str | None = None
    quantity: Money
    price: MoneyOpt = None
    currency: str
    fx_rate_to_try: Money
    fee_try: Money
    # İşaretli ve işlem anındaki kurla dondurulmuş: o gün hesaptan fiilen
    # çıkan veya giren TL budur.
    cash_amount_try: Money
    # İşlemden sonraki toplam pozisyon — grafikteki işaretçinin hover detayı.
    position_after: MoneyOpt = None


class TransactionList(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    start_date: date | None = None
    end_date: date | None = None
    transactions: list[TransactionRow]


# ---------------------------------------------------------------------------
# get_benchmark_comparison
# ---------------------------------------------------------------------------


class BenchmarkEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    return_percent: MoneyOpt = None


class AssetClassReturn(BaseModel):
    model_config = ConfigDict(frozen=True)

    asset_class: AssetClass
    return_percent: MoneyOpt = None


class BenchmarkComparison(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    window: TimeWindow
    start_date: date
    end_date: date
    truncated_to_inception: bool = False
    portfolio_return_percent: MoneyOpt = None
    by_asset_class: list[AssetClassReturn] = []
    benchmarks: list[BenchmarkEntry] = []
    # Pencere başında fiyatı olmayan varlıklar hesaba katılmaz; eksik maliyetle
    # bölmek yanlış getiri üretirdi.
    excluded_symbols: list[str] = []


# ---------------------------------------------------------------------------
# get_asset_price_history
# ---------------------------------------------------------------------------


class PricePoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: date
    close: Money


class PriceHistoryResult(BaseModel):
    """Fiyat serisi sonucu.

    Kısmi veri hata değildir: istenen pencerenin tamamı veritabanında yoksa
    eldeki kadarı döner. Grafiği hiç çizmemektense az veriyle çizmek daha iyi
    (Diyagram 03: "seçilen dönemde veri yok" ekranın geri kalanını durdurmaz).
    Bu yüzden `actual_start` ile `requested_start` ayrı tutulur — arayüz
    "veri 12.06.2026'dan itibaren mevcut" diyebilsin.
    """

    model_config = ConfigDict(frozen=True)

    # Veritabanındaki en son fiyat tarihi. CANLI FİYAT DEĞİLDİR: fiyatlar
    # günlük toplama işiyle yazılır (price_ingest), tool internete çıkmaz.
    as_of: date
    window: TimeWindow
    granularity: Granularity
    currency: PriceCurrency
    # Pencereden hesaplanan başlangıç.
    requested_start: date
    # Seride gerçekten bulunan ilk gün. Veri kısmiyse requested_start'tan geç
    # olur; hiç seri yoksa None.
    actual_start: date | None = None
    series: dict[str, list[PricePoint]] = {}
    # Varlık evreninde tanınmayan semboller.
    unknown_symbols: list[str] = []
    # Tanınan ama bu pencerede hiç fiyat kaydı olmayan semboller. Bunlar
    # `series` içinde yer almaz; birinin verisinin olmaması diğerlerinin
    # serisini engellemez.
    symbols_without_data: list[str] = []
