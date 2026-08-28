"""Kullanıcı risk profili uçlarının şemaları.

ÜRÜN SAHİBİ NOTU (Not 1 ve Not 4, 2026-08): "risk kişinin yatırım eylemidir;
yapılan test sonucu kullanıcı sisteme bildirir." Profil sistem tarafından
portföyden TÜRETİLMEZ — kullanıcı anketi doldurur, sonucu buraya bildirir,
portföy ondan sonra ona göre kurulur. Bu dosya o bildirimin sözleşmesidir.

KADEME SAYISI BİLİNÇLİ OLARAK SABİTLENMEDİ. Alanların tipi `RiskProfile`
enum'ının kendisidir, string ya da sayı değil. Profil kademesi ileride
4'ten 7'ye çıkarılırsa (karar bekliyor) bu dosyada, serviste ve uçta
DEĞİŞİKLİK GEREKMEZ: doğrulama, OpenAPI şeması ve `available_profiles`
listesi enum'dan türediği için kendiliğinden genişler. Değişmesi gereken
yerler yalnızca enum'ın kendisi, veritabanı enum'ı (migration) ve
config.py'deki profil bazlı tablolardır.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import (
    RISK_SURVEY_SCORE_MAX,
    RISK_SURVEY_SCORE_MIN,
    AssetClass,
    RiskProfile,
)


class RiskProfileUpdate(BaseModel):
    """Anket sonucunun sisteme bildirilmesi (istek gövdesi).

    Tanınmayan bir değer Pydantic tarafından 422 ile reddedilir; uçta ayrıca
    elle doğrulama yazılmadı — iki farklı hata mesajı üretmemek için."""

    model_config = ConfigDict(frozen=True)

    risk_profile: RiskProfile = Field(
        description="Anket sonucunda belirlenen risk profili",
    )


class UserRiskProfile(BaseModel):
    """Kullanıcının kayıtlı risk profili (yanıt gövdesi).

    `available_profiles` kasıtlı olarak burada dönüyor: anket ekranının
    seçenekleri kendi tarafında sabit yazmasını engeller. Kademe sayısı
    değiştiğinde arayüz kod değişikliği olmadan yeni seçenekleri görür."""

    model_config = ConfigDict(frozen=True)

    user_id: UUID
    risk_profile: RiskProfile
    available_profiles: list[RiskProfile]


class RiskSurveyUpdate(BaseModel):
    """Anket PUANININ sisteme bildirilmesi (istek gövdesi).

    `RiskProfileUpdate`'ten farkı ölçek: bu, şartnamenin 1-7'lik anket
    puanıdır ve YETKİLİ alandır — profil ondan türetilir. Aralık `Field`
    üzerinde kilitli, dolayısıyla aralık dışı bir değer servise hiç ulaşmaz
    ve 422 döner."""

    model_config = ConfigDict(frozen=True)

    risk_survey_score: int = Field(
        ge=RISK_SURVEY_SCORE_MIN,
        le=RISK_SURVEY_SCORE_MAX,
        description="Anket sonucunda çıkan risk puanı (1-7)",
    )


class UserRiskSurvey(BaseModel):
    """Kullanıcının anket puanı ve ondan türeyen profil (yanıt gövdesi).

    `risk_survey_score` `None` olabilir: kullanıcı anketi hiç doldurmamıştır.
    Bu durumda `risk_profile` yine dolu döner — kayıtlı profil ne ise odur —
    ve `score_band` `None` olur. Uydurulmuş bir puan döndürmek, kullanıcının
    beyan etmediği bir cevabı beyan etmiş göstermek olurdu (AK 5.5).

    `score_min`/`score_max` arayüzün anket ölçeğini kendi tarafında sabit
    yazmaması içindir; `available_profiles` ile aynı gerekçe.

    `score_band` puanın karşılık geldiği profilin TÜM aralığıdır (ör. 1-2).
    Arayüz "Muhafazakâr (1-2 puan)" gibi bir şey gösterebilsin diye var.
    """

    model_config = ConfigDict(frozen=True)

    user_id: UUID
    risk_survey_score: int | None
    risk_profile: RiskProfile
    score_band: tuple[int, int] | None
    score_min: int = RISK_SURVEY_SCORE_MIN
    score_max: int = RISK_SURVEY_SCORE_MAX


class RiskSurveyEvent(BaseModel):
    """Bekleyen bir anket-yeniden-doldurma OLAYININ okuma+tüketme sonucu.

    Sinyal 5'in (profil_sapmasi, Yol A — bkz. docs/notes/
    sinyal5-olay-tabanli-aktivasyon-tasarimi.md) TEK girdisi. Bu şema
    `UserRiskSurvey`'den kasıtlı olarak AYRI: o kullanıcının MEVCUT
    (statik) durumunu anlatır, bu ise bir OLAYI anlatır — aynı anda hem
    "ne şimdi doğru" hem "ne az önce değişti" sorularına aynı şemayla cevap
    vermek ikisini birbirine karıştırırdı.

    `olay_var=False` olduğunda diğer iki alan anlamsızdır (varsayılan
    değerleriyle döner) — çağıran taraf `olay_var`'a bakmadan bunları
    OKUMAMALI.
    """

    model_config = ConfigDict(frozen=True)

    olay_var: bool
    yeni_profil: RiskProfile | None = None
    # Bu OLAY sonucunda kullanıcının GÜNCEL elinde kalan ama artık yeni
    # profilin izin vermediği varlık sınıfları. `olay_var=True` olsa bile
    # boş olabilir (anket yenilendi ama hiçbir ihlal doğurmadı) — bu, sinyal
    # 5'in "yalnızca ihlal varsa üret" kuralının girdisidir.
    izin_verilmeyen_ve_elde_olan_siniflar: list[AssetClass] = Field(default_factory=list)
