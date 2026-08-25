"""Sorgudan FİYAT niyeti ve varlık sembolü çıkarır — LLM'siz, deterministik.

Piyasa Ajanı saf RAG'di: "dolar ne kadar?" sorusuna doküman aranıyor ve
"veritabanımızda bu sorguyla ilgili doğrulanmış bir bilgi bulunamadı"
dönüyordu (ölçüldü, 23 Ağustos test turu). Kur ve fiyat, dokümanlarda değil
`price_history` tablosunda yaşıyor.

Ayrımı bir LLM planlayıcısına bırakmak yerine burada kural tabanlı yapılıyor:
soru tipi ("ne kadar" / "kaç TL") ve varlık adı sonlu ve iyi tanımlı bir küme.
İkinci bir LLM çağrısı hem yanıta gecikme ekler hem de sohbetin en sık
sorulan sorusunu modelin gününe bağlardı. Kural yanılırsa RAG yolu zaten
yedek olarak duruyor.
"""

import re
from functools import lru_cache

_TURKISH_FOLD_MAP = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u"})


def _normalize(text: str) -> str:
    return text.replace("İ", "i").lower().translate(_TURKISH_FOLD_MAP)


# Kullanıcının kullandığı ad -> sembol. Uzun adlar önce denenir (bkz.
# `varlik_tespit_et`): "çeyrek altın" ile "altın" aynı cümlede geçer ve
# spesifik olan kazanmalıdır.
#
# Yalnızca kur ve kıymetli maden burada: hisse kodları zaten sembolün
# kendisiyle yazılıyor (THYAO) ve şirket adları `market_query` tarafında
# çözülüyor.
_TAKMA_ADLAR: dict[str, str] = {
    # Döviz
    "dolar": "USDTRY",
    "amerikan dolari": "USDTRY",
    "usd": "USDTRY",
    "euro": "EURTRY",
    "avro": "EURTRY",
    "eur": "EURTRY",
    "sterlin": "GBPTRY",
    "ingiliz sterlini": "GBPTRY",
    "gbp": "GBPTRY",
    "frank": "CHFTRY",
    "isvicre frangi": "CHFTRY",
    "chf": "CHFTRY",
    # Kıymetli maden — "altın" tek başına GRAM altın demektir (piyasa teamülü)
    "gram altin": "XAUTRY",
    "altin": "XAUTRY",
    "has altin": "XAUTRY",
    "ceyrek altin": "CEYREK",
    # "çeyrek" TEK BAŞINA BURAYA GİRMEZ: finansal dilde ağırlıklı anlamı
    # yılın çeyreğidir. Girseydi "Akbank'ın 2. çeyrek net kârı ne kadar?"
    # sorusu — hem "çeyrek" hem "ne kadar" eşleştiği için — çeyrek altın
    # fiyatı sorgusuna dönüşür ve çalışan bilanço yolunu bozardı (testle
    # yakalandı). Çeyrek altın soran kullanıcı zaten "çeyrek altın" der.
    "yarim altin": "YARIM",
    "tam altin": "TAMALTIN",
    "cumhuriyet altini": "CUMHUR",
    "gram gumus": "XAGTRY",
    "gumus": "XAGTRY",
    "gram platin": "XPTTRY",
    "platin": "XPTTRY",
}

# Fiyat/kur sorusunu ele veren kalıplar.
_FIYAT_KALIPLARI = (
    "ne kadar",
    "kac tl",
    "kac lira",
    "kac para",
    "fiyati",
    "fiyat",
    "kuru",
    "kur",
    "deger",
)

# Geçmişe/seyre dair soru: aynı varlık için farklı tool gerekir.
_GECMIS_KALIPLARI = (
    "gecmis",
    "seyri",
    "seyir",
    "grafik",
    "son 3 ay",
    "son uc ay",
    "son bir yil",
    "son yil",
    "son ay",
    "son hafta",
    "gecen ay",
    "gecen yil",
    "ne yapti",
    "nasil gitti",
    "degisim",
    "yukseldi",
    "dustu",
    "artti",
    "azaldi",
    "trend",
)


# Sembolün KENDİSİ gündelik bir Türkçe kelimeyle çakışıyorsa çıplak eşleşmeye
# girmez; yalnızca iki kelimelik takma adıyla ("çeyrek altın") bulunur.
#
# "2. çeyrek net kârı ne kadar?" sorusunda hem `CEYREK` sembolü hem "ne kadar"
# kalıbı eşleşiyor ve bilanço sorusu fiyat sorgusuna dönüşüyordu (testle
# yakalandı). Aynı tuzak "yarım" için de geçerli ("yarım saat", "yarım yıl").
_BELIRSIZ_SEMBOLLER = {"CEYREK", "YARIM"}


@lru_cache(maxsize=1)
def _sembol_kumesi() -> set[str]:
    """Varlık evrenindeki tüm semboller (THYAO, USDTRY, ...).

    Evren import edilemezse boş küme döner ve tespit takma adlarla sınırlı
    kalır — eksik bir import yüzünden tüm piyasa sorgularının çökmesi,
    daraltılmış bir tespitten kötüdür.
    """
    try:
        from app.providers.universe import ASSET_UNIVERSE
    except Exception:  # pragma: no cover - import hatası ortama bağlı
        return set()
    return {
        a.symbol
        for a in ASSET_UNIVERSE
        if (a.tradable or a.symbol == "XU100") and a.symbol not in _BELIRSIZ_SEMBOLLER
    }


def varlik_tespit_et(query: str) -> list[str]:
    """Sorguda geçen varlıkların sembollerini döndürür (sırayı korur).

    Uzun takma adlar önce denenir: "çeyrek altın" sorgusunda hem "ceyrek
    altin" hem "altin" eşleşir ve spesifik olan kazanmalıdır — aksi hâlde
    çeyrek altın soran kullanıcıya gram altın fiyatı dönerdi.
    """
    normalized = _normalize(query)
    bulunan: list[str] = []

    for ad in sorted(_TAKMA_ADLAR, key=len, reverse=True):
        if re.search(rf"\b{re.escape(ad)}\b", normalized):
            sembol = _TAKMA_ADLAR[ad]
            if sembol not in bulunan:
                bulunan.append(sembol)
            # Eşleşen adı metinden çıkar: "çeyrek altın" yakalandıktan sonra
            # içindeki "altın" ikinci kez eşleşmemeli.
            normalized = normalized.replace(ad, " ")

    # Sembolün kendisiyle yazılmış varlıklar (THYAO, USDTRY, XAUTRY...).
    for sembol in sorted(_sembol_kumesi(), key=len, reverse=True):
        if re.search(rf"\b{re.escape(_normalize(sembol))}\b", normalized):
            if sembol not in bulunan:
                bulunan.append(sembol)

    return bulunan


def _icerir(normalized: str, kaliplar: tuple[str, ...]) -> bool:
    return any(k in normalized for k in kaliplar)


def fiyat_niyeti(query: str) -> dict | None:
    """Fiyat sorusuysa `{"symbols": [...], "history": bool}`, değilse None.

    İki şart birlikte aranır: SORU fiyat/kur soruyor OLMALI ve bir varlık
    ADIYLA anılmalı. Tek başına "ne kadar" bir portföy sorusu olabilir
    ("portföyüm ne kadar"), tek başına "dolar" ise haber sorusu olabilir
    ("dolar hakkında haberler"). İkisi birlikteyken niyet nettir.
    """
    normalized = _normalize(query)
    semboller = varlik_tespit_et(query)
    if not semboller:
        return None

    gecmis = _icerir(normalized, _GECMIS_KALIPLARI)
    if not gecmis and not _icerir(normalized, _FIYAT_KALIPLARI):
        return None

    return {"symbols": semboller, "history": gecmis}
