"""Risk değerlendirmesi ve yeniden dengeleme önerisiyle ilgili ekip sözleşmesi.
Frontend'deki src/types/ altındaki TypeScript tipleri bu şemayla eşleşmelidir.

Tüm sayısal alanlar `app/services/risk_service.py` tarafından hesaplanır;
hiçbiri LLM tarafından üretilmez (CLAUDE.md §4 "uydurmama ilkesi")."""

from datetime import date
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.config import AssetClass, RiskLevel, RiskProfile
from app.schemas.portfolio import Money

# CLAUDE.md §4: her finansal çıktı bu ibareyi taşımak zorundadır. Tek yerde
# tanımlı ki metin değişirse her yerde birlikte değişsin.
INVESTMENT_DISCLAIMER = (
    "Bu bir yatırım tavsiyesi değildir. Sunulan analiz ve öneriler yalnızca "
    "bilgilendirme amaçlıdır; yatırım kararlarınızdan siz sorumlusunuz."
)


class RiskProfileSource(str, Enum):
    """Değerlendirmede kullanılan risk profilinin nereden geldiği. Arayüz,
    `OVERRIDE` durumunda 'geçici olarak X profiline göre hesaplandı' uyarısı
    gösterebilsin diye döndürülür."""

    USER = "user"
    OVERRIDE = "override"


class RebalanceActionType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class CorrelationPair(BaseModel):
    """İki varlık arasındaki Pearson korelasyon katsayısı (-1..1)."""

    model_config = ConfigDict(frozen=True)

    asset_symbol_a: str
    asset_symbol_b: str
    correlation: Money


class RiskMetrics(BaseModel):
    """Ham ölçümler. Skor bunlardan türetilir; arayüz skoru açıklamak için
    bu alanları gösterebilir."""

    model_config = ConfigDict(frozen=True)

    # Yeterli fiyat geçmişi yoksa (bkz. Settings.risk_min_price_points) bu
    # alanların tamamı `null` döner — tahmini bir değerle doldurulmaz.
    annualized_volatility_percent: Money | None
    max_drawdown_percent: Money | None
    # Kovaryans matrisi üzerinden hesaplanan yıllık portföy volatilitesi
    # (AK 2.3). annualized_volatility_percent (tarihsel değer serisinden
    # doğrudan) ile yakın olmalı ama birebir aynı olmak zorunda değildir —
    # ikisi farklı yöntemlerdir, ikisi de gösterilir (izlenebilirlik).
    covariance_volatility_percent: Money | None
    correlation_matrix: list[CorrelationPair]

    # VaR (Value at Risk, AK 2.4): belirtilen güven seviyesinde, belirtilen
    # ufukta beklenen en kötü zarar (TRY ve yüzde olarak, pozitif sayı).
    value_at_risk_try: Money | None
    value_at_risk_percent: Money | None
    value_at_risk_confidence: Money
    value_at_risk_horizon_days: int

    # Sharpe oranı (AK 2.5): (yıllık getiri - risksiz oran) / yıllık volatilite.
    sharpe_ratio: Money | None
    risk_free_rate_percent: Money
    risk_free_rate_is_live: bool

    max_asset_weight_percent: Money
    max_asset_symbol: str | None
    max_class_weight_percent: Money
    max_class: AssetClass | None

    # Herfindahl-Hirschman endeksi (Σ ağırlık²) ve onun tersi olan "etkin
    # varlık sayısı": 10 varlığın 9'u toplam %5'lik ağırlıktaysa etkin sayı
    # 10 değil ~1'dir.
    herfindahl_index: Money
    effective_holdings_count: Money

    # Varlık sınıfı bazlı temel risk skorunun (BR: hisse=yüksek, tahvil=düşük
    # vb.) portföy ağırlıklarıyla harmanlanmış hali (0-100).
    asset_class_base_risk_score: Money

    holdings_count: int
    asset_class_count: int
    # Volatilite/korelasyon hesabında kullanılan ortak fiyat günü sayısı
    # (izlenebilirlik).
    price_points_used: int


class RebalanceAction(BaseModel):
    """Tek bir varlık sınıfı için yeniden dengeleme önerisi."""

    model_config = ConfigDict(frozen=True)

    asset_class: AssetClass
    current_percent: Money
    target_percent: Money
    # Hedef - mevcut. Pozitifse alım, negatifse satım yönünde.
    delta_percent: Money
    delta_amount: Money
    action: RebalanceActionType


class RiskAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    as_of: date
    risk_profile: RiskProfile
    risk_profile_source: RiskProfileSource
    total_value: Money

    # Boş portföyde skor ve etiket `null` döner: risk ölçülemiyorsa
    # uydurulmaz (CLAUDE.md §4 "uydurmama ilkesi"). Sebep `warnings`'te yazar.
    risk_score: Money | None
    risk_level: RiskLevel | None

    metrics: RiskMetrics
    rebalance_actions: list[RebalanceAction]
    is_balanced: bool

    # Kullanıcıya gösterilecek uyarılar (boş portföy, yetersiz fiyat verisi vb.).
    warnings: list[str]
    disclaimer: str = INVESTMENT_DISCLAIMER
