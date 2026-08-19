"""Risk değerlendirmesi ve yeniden dengeleme önerisiyle ilgili ekip sözleşmesi.
Frontend'deki src/types/ altındaki TypeScript tipleri bu şemayla eşleşmelidir.

Tüm sayısal alanlar `app/services/risk_service.py` tarafından hesaplanır;
hiçbiri LLM tarafından üretilmez (CLAUDE.md §4 "uydurmama ilkesi").

v2 (Risk/Strateji Ajanı analist belgesi): risk seviyesi artık kategori bazlı
(Hisse/Altın/Döviz/Tahvil/Nakit) yıllık portföy volatilitesinden gelen 7
kademeli bir etikettir; eski 0-100 kompozit `risk_score` ve profil hedef
yüzdesine dayanan basit `RebalanceAction` kaldırıldı. Yerlerini
`RiskCauseDiagnosis` (risk neden yüksek çıktı) ve `RebalanceScenario` (kural
tabanlı simülasyon) aldı."""

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


class CategoryCorrelationPair(BaseModel):
    """İki kategori arasındaki Pearson korelasyon katsayısı (-1..1). Varlık
    değil KATEGORİ bazlıdır (Hisse/Altın/Döviz/Tahvil/Nakit) — sabit 5x5
    matris, N varlık için NxN değil."""

    model_config = ConfigDict(frozen=True)

    category_a: AssetClass
    category_b: AssetClass
    correlation: Money


class CategoryMetrics(BaseModel):
    """Tek bir kategori için hesaplanan değerler. Kategorinin günlük getirisi,
    o kategorideki varlıkların TL ağırlıklı ortalamasıdır."""

    model_config = ConfigDict(frozen=True)

    asset_class: AssetClass
    weight_percent: Money
    annualized_volatility_percent: Money | None
    # Bu kategorinin portföy VARYANSINA katkısı (RC%, oran toplamı 1'e
    # yakındır). Aksiyon B'nin "en yüksek RC%'li kategoriden al" kuralında
    # ve kök neden teşhisinde kullanılır.
    risk_contribution_percent: Money | None


class ConcentrationCause(BaseModel):
    """Neden A — Yoğunlaşma: tek bir varlık/kategori portföyün çok büyük
    kısmını mı oluşturuyor?"""

    model_config = ConfigDict(frozen=True)

    triggered: bool
    max_asset_weight_percent: Money
    max_asset_symbol: str | None
    max_category_weight_percent: Money
    max_category: AssetClass | None
    herfindahl_index: Money


class HighVolatilityAssetCause(BaseModel):
    """Neden B — Yüksek volatiliteli varlık: kendi başına yüksek volatiliteye
    sahip bir varlık/kategori riski orantısız mı taşıyor?"""

    model_config = ConfigDict(frozen=True)

    triggered: bool
    # Yıllık volatilitesi eşiği aşan varlıkların toplam ağırlığı.
    high_volatility_assets_weight_percent: Money
    max_risk_contribution_category: AssetClass | None
    max_risk_contribution_percent: Money | None


class CorrelationCause(BaseModel):
    """Neden C — Korelasyon: portföydeki kategoriler birlikte mi hareket
    ediyor, çeşitlendirme zayıf mı?"""

    model_config = ConfigDict(frozen=True)

    triggered: bool
    highest_correlated_pair: CategoryCorrelationPair | None
    diversification_ratio: Money | None
    herfindahl_index: Money


class RiskCauseDiagnosis(BaseModel):
    """Yalnızca portföyün volatilitesi kullanıcının risk profili için
    beklenen bandın üzerindeyken hesaplanır (bkz.
    risk_service._diagnose_causes); aksi halde `RiskAssessment.causes`
    None'dır."""

    model_config = ConfigDict(frozen=True)

    concentration: ConcentrationCause
    high_volatility_asset: HighVolatilityAssetCause
    correlation: CorrelationCause


class ScenarioCategoryWeight(BaseModel):
    model_config = ConfigDict(frozen=True)

    asset_class: AssetClass
    current_percent: Money
    proposed_percent: Money


class ScenarioAssetWeight(BaseModel):
    """Kategori ağırlığı değiştiğinde, o kategorideki her varlığın oransal
    ölçeklenmiş hâli (bkz. belge 6.5). Kategoride hiç varlık yoksa bu liste
    boş kalır, yalnızca kategori kırılımı gösterilir."""

    model_config = ConfigDict(frozen=True)

    asset_symbol: str
    asset_class: AssetClass
    current_percent: Money
    proposed_percent: Money
    current_value: Money
    proposed_value: Money


class RebalanceScenario(BaseModel):
    """Kural tabanlı, deterministik bir simülasyondur (KS-1, KS-2): portföyü
    DEĞİŞTİRMEZ, yalnızca alternatif bir ağırlık dağılımı gösterir. Hangi
    varlığın alınıp satılacağını, beklenen getiriyi veya fiyat tahminini asla
    içermez."""

    model_config = ConfigDict(frozen=True)

    # Uygulanan aksiyonlar, her zaman A→B→C sırasıyla (KK-1). Örn. ["A", "B"].
    actions_applied: list[str]
    label: str  # "Küçük Düzeltme" | "Dengeli Düzeltme" | "Belirgin Düzeltme"
    category_weights: list[ScenarioCategoryWeight]
    asset_weights: list[ScenarioAssetWeight]
    volatility_before_percent: Money
    volatility_after_percent: Money
    risk_level_before: RiskLevel
    risk_level_after: RiskLevel
    turnover_percent: Money
    score: Money


class RiskMetrics(BaseModel):
    """Ham ölçümler. Risk seviyesi bunlardan türetilir; arayüz seviyeyi
    açıklamak için bu alanları gösterebilir."""

    model_config = ConfigDict(frozen=True)

    # Yeterli fiyat geçmişi yoksa (bkz. Settings.risk_min_price_points) bu
    # alanların tamamı `null` döner — tahmini bir değerle doldurulmaz (AK 2.7).
    annualized_volatility_percent: Money | None
    max_drawdown_percent: Money | None
    category_metrics: list[CategoryMetrics]
    category_correlation_matrix: list[CategoryCorrelationPair]
    # DR = (Σ wᵢ×σᵢ) / σ_portföy. 1'e yakınsa çeşitlendirme etkisi zayıf,
    # büyüdükçe (>1) çeşitlendirme riski azaltıyor demektir.
    diversification_ratio: Money | None

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

    # Yoğunlaşma ölçütleri — risk seviyesine karışmaz, yalnızca teşhis ve
    # izlenebilirlik için gösterilir.
    max_asset_weight_percent: Money
    max_asset_symbol: str | None
    max_class_weight_percent: Money
    max_class: AssetClass | None
    herfindahl_index: Money

    holdings_count: int
    asset_class_count: int
    # Volatilite/korelasyon hesabında kullanılan ortak fiyat günü sayısı
    # (izlenebilirlik).
    price_points_used: int


class RiskAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    as_of: date
    risk_profile: RiskProfile
    risk_profile_source: RiskProfileSource
    total_value: Money

    # Volatilite hesaplanamıyorsa (AK 2.7, boş portföy vb.) `null` döner:
    # risk ölçülemiyorsa uydurulmaz (CLAUDE.md §4). Sebep `warnings`'te yazar.
    risk_level: RiskLevel | None
    # Volatilite, kullanıcının risk profili için beklenen bandın (bkz.
    # RISK_TARGET_VOLATILITY_BAND) üzerinde mi? Hesaplanamıyorsa None.
    is_within_profile: bool | None

    metrics: RiskMetrics
    # Yalnızca is_within_profile=False iken dolu; aksi halde None.
    causes: RiskCauseDiagnosis | None
    # Yalnızca `include_scenarios=True` istenmişse VE is_within_profile=False
    # VE en az bir uygun senaryo bulunmuşsa dolu; aksi halde boş liste.
    scenarios: list[RebalanceScenario]

    # Kullanıcıya gösterilecek uyarılar (boş portföy, yetersiz fiyat verisi vb.).
    warnings: list[str]
    disclaimer: str = INVESTMENT_DISCLAIMER
