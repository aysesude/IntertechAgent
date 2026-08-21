"""Varlık sınıfı tavsiye uygunluğu — İŞ ANALİSTİ ŞARTNAMESİ (2026-08).

Kural aynen şöyle tanımlı: "Kullanıcıların çözdüğü anket sonucu 1-7 arası bir
risk puanı olur. Aşağıdaki risk seviyesi kullanıcının risk seviyesinden
büyükse kişi o varlık türünden satın alım ya da yatırım TAVSİYESİ alamaz."

KAPSAM — dikkatle okunmalı. Kural TAVSİYEYİ kısıtlar, SAHİPLİĞİ değil.
Puanı 3 olan bir kullanıcının portföyünde hisse BULUNABİLİR (geçmişten
kalmış olabilir, sistem dışında alınmış olabilir); sistem o kullanıcıya
hisse yönünde bir tavsiye ÜRETMEZ, ama var olan hissesini gizlemez,
raporlamadan düşürmez ve sahipliği "hata" olarak işaretlemez.

Bu, Ürün Sahibi'nin 3. notundan ("kişinin risk profili uymuyorsa zaten
hissesi olmamalı") daha yumuşak bir yorumdur ve bilinçli tercih değildir —
iki metin farklı sertlikte ve çelişki HENÜZ ÇÖZÜLMEDİ. Şartname yazılı
kaynak olduğu için burada şartnamenin lafzı uygulanmıştır. Karar
netleştiğinde değişmesi gereken tek yer bu modüldür.

Neden ayrı bir modül: bu kural risk ölçümünden (volatilite, korelasyon, VaR)
tamamen bağımsızdır — girdisi yalnızca anket puanı ve varlık sınıfıdır,
fiyat geçmişine hiç bakmaz. risk_service'in içine gömülseydi, o dosyanın
metodolojisi değiştiğinde (ki şartnamede o bölüm gözden geçiriliyor) bu
kural da gereksiz yere etkilenirdi.
"""

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
