"""Risk değerlendirmesi ve yeniden dengeleme önerisiyle ilgili ekip sözleşmesi.
Frontend'deki src/types/ altındaki TypeScript tipleri bu şemayla eşleşmelidir.

Tüm sayısal alanlar `app/services/risk_service.py` tarafından hesaplanır;
hiçbiri LLM tarafından üretilmez (CLAUDE.md §4 "uydurmama ilkesi").

v2 (Risk/Strateji Ajanı analist belgesi): risk seviyesi artık kategori bazlı
(Hisse/Altın/Döviz/Tahvil/Nakit) yıllık portföy volatilitesinden gelen 7
kademeli bir etikettir; eski 0-100 kompozit `risk_score` ve profil hedef
yüzdesine dayanan basit `RebalanceAction` kaldırıldı. Yerlerini
`RiskCauseDiagnosis` (risk neden yüksek çıktı) ve `RebalanceScenario` (kural
tabanlı simülasyon) aldı.

2026-08 eki: `RiskMetrics.asset_metrics` — iş analistinin "portföydeki
varlıkların tek tek risk durumu" talebi. Bu, kategori-bazlı v2 metodolojisini
GERİ ALMAZ: yalnızca her varlığın kendi volatilitesini ve etiketini taşır,
NxN korelasyon/katkı hesaplamaz (bkz. AssetRiskMetrics docstring'i)."""

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


class AssetRiskMetrics(BaseModel):
    """Tek bir VARLIĞIN (kategori değil) risk durumu — iş analistinin 2026-08
    talebi: "portföydeki varlıkların tek tek risk durumunu hesaplama".

    KASITLI OLARAK `risk_contribution_percent` YOK: portföy varyansına katkı,
    varlıklar arası NxN korelasyon matrisi gerektirir; v2 metodolojisi
    bilinçli olarak yalnızca 5x5 KATEGORİ matrisini hesaplıyor (bkz. bu
    dosyanın v2 notu ve risk_service.py'nin modül docstring'i — "Kapsam
    sınırlaması"). Bu alan varlığın KENDİ volatilitesini ve ondan türeyen
    etiketi taşır; portföyün risk kaynağı analizi hâlâ `RiskCauseDiagnosis`
    ve kategori düzeyindeki `CategoryMetrics.risk_contribution_percent`'te.

    `risk_level`, `RISK_LEVEL_VOLATILITY_UPPER_BOUNDS` ile — kategori/portföy
    volatilitesiyle AYNI merdivenle — hesaplanır (bkz. scripts/varlik_risk_
    olcum.py: temiz veri üzerinde bu merdiven varlık düzeyinde de 6/7 kademeyi
    anlamlı şekilde ayrıştırıyor; ayrı bir varlık-bazlı tablo gerekmedi)."""

    model_config = ConfigDict(frozen=True)

    asset_symbol: str
    asset_class: AssetClass
    weight_percent: Money
    # Yeterli ortak fiyat günü yoksa (bkz. Settings.risk_min_price_points)
    # None döner — tahmini bir değerle doldurulmaz (AK 2.7).
    annualized_volatility_percent: Money | None
    risk_level: RiskLevel | None


class ConcentrationCause(BaseModel):
    """Neden A — Yoğunlaşma: tek bir varlık/kategori portföyün çok büyük
    kısmını mı oluşturuyor?

    2026-08-31 eki: `triggered` üç ayrı koşulun OR'u olduğu için hangisinin
    tetiklendiği kayboluyordu; kullanıcıya "yoğunlaşma var" denebiliyor ama
    NEYE göre yoğunlaştığı (tek varlık mı, tek sınıf mı) söylenemiyordu.
    Aşağıdaki üç bayrak bu ayrımı taşıyor. Karar burada, SERVİSTE veriliyor;
    ajan eşikleri yeniden hesaplamıyor (iki katmanın çelişmemesi ilkesi,
    bkz. `agents/risk_agent.py::_profile_position`).

    SEKTÖR BAZLI YOĞUNLAŞMA BURADA YOKTUR ve ölçülmüyor: `Asset`'te sektör
    alanı yok, ajana sektör verisi hiç gitmiyor. `risk_signals.md`'deki
    `sektor_yogunlasmasi` sinyali de bu yüzden fiilen hiç tetiklenmiyor."""

    model_config = ConfigDict(frozen=True)

    triggered: bool
    # Hangi bazda tetiklendi. `triggered` bu üçünün OR'udur; hiçbiri
    # tetiklenmemişse `triggered` da False'tur.
    #
    # `hhi_triggered` bir "hangisi" bilgisi DEĞİLDİR: tek bir varlık ya da
    # sınıf eşiği aşmasa bile portföyün az sayıda kaleme dağılmış olduğunu
    # söyler. Kullanıcıya tek bir sembol/sınıf adıyla değil, dağılımın
    # geneliyle anlatılmalıdır.
    asset_triggered: bool
    category_triggered: bool
    hhi_triggered: bool
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
    # Varlık düzeyinde kırılım — bkz. AssetRiskMetrics docstring'i. Elde
    # tutulan her varlık için bir kayıt (volatilite hesaplanamıyorsa dahi;
    # o durumda yalnızca annualized_volatility_percent/risk_level None'dır).
    asset_metrics: list[AssetRiskMetrics]
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


class MismatchedHolding(BaseModel):
    """Kullanıcının elinde olan ama anket puanının izin vermediği bir varlık.

    Bu bir RİSK ÖLÇÜMÜ DEĞİLDİR — volatiliteyle hiçbir ilgisi yok. Kuralın
    sahibi `advice_eligibility` (girdisi yalnızca anket puanı + varlığın
    uygunluk seviyesi). Risk değerlendirmesinin İÇİNDE taşınmasının tek
    sebebi, o serviste portföyün ve anket puanının zaten yüklü olması: aynı
    bilgi için ikinci bir tool çağrısı ya da sorgu gerekmesin.

    `advice_risk_level` VARLIK düzeyidir ve sınıf varsayılanından ayrılabilir
    (bkz. advice_eligibility "Varlık düzeyi"): BHE serbest fonu STOCK
    sınıfındadır ama kendi seviyesi 7'dir."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    asset_class: AssetClass
    advice_risk_level: int


class RiskAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    as_of: date
    risk_profile: RiskProfile
    risk_profile_source: RiskProfileSource
    # Kullanıcının ANKET PUANI (1-7) — profilin türediği yetkili alan.
    #
    # `risk_profile` ile birlikte dönüyor çünkü ikisi aynı şeyin iki
    # gösterimi: puan yetkili, profil ondan türer
    # (`config.risk_profile_for_survey_score`). Arayüzün "Risk Profili"
    # kartı puanı gösteriyor; ayrı bir uç çağırmak zorunda kalmasın diye
    # burada, `risk_profile`'ın yanında.
    #
    # `None` olabilir: kullanıcı anketi hiç doldurmamıştır. Uydurulmaz —
    # profilden geriye puan üretmek, verilmemiş bir cevabı verilmiş
    # göstermek olurdu (AK 5.5). `profile_override` ile hesaplandığında da
    # `None` döner: o senaryoda profil kullanıcının beyanı değildir.
    risk_survey_score: int | None
    total_value: Money

    # Volatilite hesaplanamıyorsa (AK 2.7, boş portföy vb.) `null` döner:
    # risk ölçülemiyorsa uydurulmaz (CLAUDE.md §4). Sebep `warnings`'te yazar.
    risk_level: RiskLevel | None
    # Volatilite, kullanıcının risk profili için beklenen bandın (bkz.
    # RISK_TARGET_VOLATILITY_BAND) üzerinde mi? Hesaplanamıyorsa None.
    is_within_profile: bool | None

    # Elde olan ama anket puanının izin vermediği varlıklar (VARLIK düzeyi,
    # bkz. MismatchedHolding). `is_within_profile`'dan BAĞIMSIZDIR: bandın
    # içindeki bir portföyde de dolu olabilir — biri oynaklık ölçer, bu
    # ürün uygunluğuna bakar (bkz. docs/notes/analiste-kapsam-sapmalari.md
    # madde 7, "iki ayrı 1-7 ölçeği").
    #
    # Anket hiç doldurulmamışsa (`risk_survey_score is None`) ya da
    # `profile_override` ile hesaplanmışsa BOŞ döner: puan yoksa uyumsuzluk
    # da hesaplanamaz, uydurulmaz.
    mismatched_holdings: list[MismatchedHolding]

    metrics: RiskMetrics
    # Volatilite hesaplanabildiği her portföyde dolu; hesaplanamıyorsa
    # (boş portföy, yetersiz fiyat geçmişi) None.
    #
    # 2026-08-31'e kadar yalnızca is_within_profile=False iken doluydu.
    # Bandın içindeki portföylerde yoğunlaşma hiç görünmüyordu; koşul
    # kaldırıldı. DOLU OLMASI "risk var" demek değildir — her nedenin kendi
    # `triggered` bayrağı var ve eşikler değişmedi.
    causes: RiskCauseDiagnosis | None
    # Yalnızca `include_scenarios=True` istenmişse VE is_within_profile=False
    # VE en az bir uygun senaryo bulunmuşsa dolu; aksi halde boş liste.
    scenarios: list[RebalanceScenario]

    # Kullanıcıya gösterilecek uyarılar (boş portföy, yetersiz fiyat verisi vb.).
    warnings: list[str]
    disclaimer: str = INVESTMENT_DISCLAIMER
