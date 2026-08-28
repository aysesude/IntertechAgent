"""Yatırımcı risk profili anketinin ekip sözleşmesi.

Sorular ve seçenekler ŞEMADA SABİT DEĞİL: `data/risk_survey_config.json`'dan
okunup olduğu gibi arayüze taşınır. Soru metnini TypeScript'e kopyalamak, tek
doğruluk kaynağı kuralını ilk düzenlemede bozardı — biri JSON'u değiştirir,
arayüz eski soruyu sormaya devam eder ve skor sorulmayan bir soruya göre
hesaplanır.

Cevap değerleri de serbest sözlük: `{"B1": "c", "E1": {"r1": {...}}}`.
Doğrulama şemada değil `survey_service` içinde yapılıyor, çünkü geçerli
seçenek kümesi yine config'ten geliyor.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict


class SurveyQuestions(BaseModel):
    """Anket içeriği — arayüz formu bundan çizer.

    Config'in tamamı değil, arayüzün ihtiyacı olan bölümler: meta bilgi,
    sorular, ürün matrisi ve profil tanımları. Ağırlıklar (`o[2]`) de
    geliyor; gizlemenin bir anlamı yok (skorlama sunucuda) ve ayıklamak
    config'i iki yerde tanımlamak demek olurdu.
    """

    model_config = ConfigDict(frozen=True)

    meta: dict[str, Any]
    sorular: dict[str, Any]
    urun_matrisi: dict[str, Any]
    profiller: list[dict[str, Any]]
    arac_sirasi: list[str] = []
    araclar: dict[str, Any] = {}


class SurveyRule(BaseModel):
    """Tetiklenen tutarlılık kuralı.

    `durdurucu` ise profil ÜRETİLMEZ ve kullanıcıdan cevaplarını gözden
    geçirmesi istenir.
    """

    model_config = ConfigDict(frozen=True)

    kod: str
    durdurucu: bool
    mesaj: str


class SurveyResult(BaseModel):
    """Skorlama çıktısı.

    `profil_seviyesi` doğrudan `users.risk_survey_score` olarak yazılır
    (ikisi de 1-7). `sonuc_uretildi` `False` iken profil alanları `None`
    gelir — arayüz bu durumda profil GÖSTERMEZ.
    """

    model_config = ConfigDict(frozen=True)

    kapasite: int
    tolerans: int
    bilgi: int
    nihai_skor: int
    profil_seviyesi: int | None
    profil_adi: str
    azami_fon_risk_degeri: int | None
    azami_urun_risk_kategorisi: int | None
    ornek_dagilim: dict[str, int] | None
    bilgi_nedeniyle_kisitlandi: bool
    likidite_tavani_uygulandi: bool
    sinir_bolgesinde: bool
    kurallar: list[SurveyRule]
    sonuc_uretildi: bool
    # Sonucu kullanıcının KENDİ cevaplarına bağlayan olgular. Deterministik
    # üretilir (`survey_service._gerekceler`), LLM'e sorulmaz: hangi cevabın
    # sonucu belirlediği ölçülmüş bir bilgidir, tahmin edilemez. `yorum` bu
    # olguları cümleye döker; sağlayıcı düşerse liste yine de gelir.
    gerekceler: list[str] = []
    # Sonucu kişiselleştiren metin. LLM üretir; ulaşılamazsa profil adından
    # türetilmiş sabit bir metne düşer, ASLA boş kalmaz.
    yorum: str


class SurveyScoreRequest(BaseModel):
    """Kayıt öncesi önizleme skorlaması.

    Kimlik doğrulaması İSTEMEZ: kayıt akışının içinde, kullanıcı henüz
    yokken çağrılıyor. Hiçbir şey yazmaz, saf hesaptır.
    """

    model_config = ConfigDict(frozen=True)

    answers: dict[str, Any]
