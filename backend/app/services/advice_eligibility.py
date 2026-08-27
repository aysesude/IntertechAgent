"""Varlık sınıfı tavsiye uygunluğu — İŞ ANALİSTİ ŞARTNAMESİ (2026-08).

Kural aynen şöyle tanımlı: "Kullanıcıların çözdüğü anket sonucu 1-7 arası bir
risk puanı olur. Aşağıdaki risk seviyesi kullanıcının risk seviyesinden
büyükse kişi o varlık türünden satın alım ya da yatırım TAVSİYESİ alamaz."

KAPSAM (iş analistiyle netleştirildi, 2026-08-21): kural HEM SAHİPLİĞİ HEM
TAVSİYEYİ kapsar — "hem sahip olamaz hem tavsiye de alamaz, hiçbir şekilde
önermez". Yani izinli olmayan bir sınıf:
  - hiçbir öneride/senaryoda yer ALMAZ,
  - portföyde fiilen bulunuyorsa profil UYUMSUZLUĞU sayılır.

Uyumsuzluk bulunduğunda sistem zorla satış yapmaz, yapamaz; Ürün Sahibi'nin
2. notu gereği yalnızca UYARIR. Yani "sahip olamaz" pratikte "sahipse bu
durum kullanıcıya açıkça bildirilir" demektir — sessizce gizlemek de,
portföyden düşmek de yanlış olur.

Bu yorum Ürün Sahibi'nin 3. notuyla ("kişinin risk profili uymuyorsa zaten
hissesi olmamalı") aynı yöndedir; daha önce şartnamenin lafzı ("tavsiye
alamaz") ile arasında görülen fark böylece kapanmıştır.

Ayrıca: profil YALNIZCA hangi kategorilere izin verildiğini söyler; kategori
ağırlıklarıyla (yüzdelerle) hiçbir ilişkisi yoktur (iş analisti,
2026-08-21). Bu yüzden burada hiçbir ağırlık/yüzde eşiği yer almaz.

Neden ayrı bir modül: bu kural risk ölçümünden (volatilite, korelasyon, VaR)
tamamen bağımsızdır — girdisi yalnızca anket puanı ve varlık sınıfıdır,
fiyat geçmişine hiç bakmaz. risk_service'in içine gömülseydi, o dosyanın
metodolojisi değiştiğinde (ki şartnamede o bölüm gözden geçiriliyor) bu
kural da gereksiz yere etkilenirdi.
"""

from functools import lru_cache

from app.core.config import (
    ASSET_CLASS_ADVICE_RISK_LEVEL,
    RISK_SURVEY_SCORE_MAX,
    RISK_SURVEY_SCORE_MIN,
    AssetClass,
)


def validate_survey_score(survey_score: int) -> int:
    """Anket puanını doğrular. Aralık dışıysa ValueError.

    Sessizce sınıra çekmek (clamp) KASITLI OLARAK yapılmıyor: 9 puanlık bir
    girdi bir hesap hatasıdır ve 7'ye çekilirse kullanıcıya hak etmediği
    genişlikte tavsiye üretilir. Hata görünür olmalı."""
    if not RISK_SURVEY_SCORE_MIN <= survey_score <= RISK_SURVEY_SCORE_MAX:
        raise ValueError(
            f"Anket risk puani {RISK_SURVEY_SCORE_MIN}-{RISK_SURVEY_SCORE_MAX} "
            f"araliginda olmali, gelen deger: {survey_score}"
        )
    return survey_score


def is_advice_allowed(asset_class: AssetClass, survey_score: int) -> bool:
    """O varlık sınıfı için tavsiye üretilebilir mi?

    Karşılaştırma `<=`: seviyesi puana EŞİT olan sınıf serbesttir, yalnızca
    puandan BÜYÜK olan yasaktır ("büyükse ... tavsiye alamaz")."""
    validate_survey_score(survey_score)
    return ASSET_CLASS_ADVICE_RISK_LEVEL[asset_class] <= survey_score


def allowed_asset_classes(survey_score: int) -> set[AssetClass]:
    """Anket puanına göre tavsiye üretilebilecek varlık sınıfları."""
    validate_survey_score(survey_score)
    return {ac for ac in AssetClass if ASSET_CLASS_ADVICE_RISK_LEVEL[ac] <= survey_score}


def blocked_asset_classes(survey_score: int) -> set[AssetClass]:
    """Anket puanına göre tavsiye üretilemeyecek varlık sınıfları.

    Çağıran taraf bunu kullanıcıya BİLDİRMELİDİR. Sessizce eleme, kullanıcıya
    eksik bir liste gösterip nedenini saklamak olurdu; şartname çıktının her
    bölümünde gerekçenin somut olmasını istiyor."""
    validate_survey_score(survey_score)
    return set(AssetClass) - allowed_asset_classes(survey_score)


# --- Varlık düzeyi ---------------------------------------------------------
#
# Sınıf tablosu TİPİK varlığı tarif eder; tek tek varlıklar ondan ayrılabilir
# ve ayrılıyorlar da (`providers/universe.AssetSpec.risk_level`):
#
#   IOO  para piyasası fonu   sınıfı BOND=2, kendisi 1
#   AKE  eurobond fonu        sınıfı BOND=2, kendisi 3
#   AFT  yabancı hisse fonu   sınıfı STOCK=5, kendisi 6
#   AAPL ABD hissesi          sınıfı STOCK=5, kendisi 6
#
# Bu yüzden bir varlığın uygunluğuna karar verirken sınıf fonksiyonları
# (`is_advice_allowed`) DEĞİL, buradakiler kullanılmalıdır. Sınıf
# fonksiyonları kaba görünüm içindir ve şartname metnine bire bir karşılık
# geldiği için korunuyor.


@lru_cache(maxsize=1)
def _asset_risk_levels() -> dict[str, int]:
    """`{sembol: seviye}` — yalnızca sınıfından AYRILAN varlıklar.

    Evren import edilemezse boş sözlük döner ve her varlık sınıf
    varsayılanına düşer. Bir import hatası yüzünden uygunluk kontrolünün
    tamamen çökmesi, kaba ama çalışan bir sonuçtan kötüdür (zarif düşüş).
    """
    try:
        from app.providers.universe import ASSET_UNIVERSE
    except Exception:  # pragma: no cover - import hatası ortama bağlı
        return {}
    return {spec.symbol: spec.risk_level for spec in ASSET_UNIVERSE if spec.risk_level is not None}


def asset_risk_level(symbol: str, asset_class: AssetClass) -> int:
    """Varlığın etkin uygunluk seviyesi: varlık istisnası varsa o, yoksa sınıf.

    `asset_class` ayrıca isteniyor ki çağıran taraf DB'deki `Asset` satırıyla
    (sembol + sınıf) çalışabilsin; evrende bulunmayan bir sembol — ör. elle
    eklenmiş bir kayıt — sessizce sınıf varsayılanına düşer.
    """
    return _asset_risk_levels().get(symbol, ASSET_CLASS_ADVICE_RISK_LEVEL[asset_class])


def is_asset_advice_allowed(symbol: str, asset_class: AssetClass, survey_score: int) -> bool:
    """O VARLIK için tavsiye üretilebilir mi?

    Karşılaştırma sınıf sürümüyle aynı (`<=`): seviyesi puana eşit olan
    varlık serbesttir, yalnızca puandan büyük olan yasaktır.
    """
    validate_survey_score(survey_score)
    return asset_risk_level(symbol, asset_class) <= survey_score
