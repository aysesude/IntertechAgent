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

# "â" da dahildir ("kâr" -> "kar"): eksikliği ölçümle doğrulandı (bkz.
# rag/retriever.py'deki aynı düzeltme) — "kârı" hiç foldlanmadığı için
# "brüt kârı ne kadar" gibi bir içerik sorusu, _ICERIK_KELIMELERI_RE'deki
# "brut kar" kalıbıyla eşleşemeyip yanlışlıkla fiyat sorgusu sayılıyordu.
_TURKISH_FOLD_MAP = str.maketrans(
    {"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a", "î": "i", "û": "u"}
)


def _normalize(text: str) -> str:
    return text.replace("İ", "i").lower().translate(_TURKISH_FOLD_MAP)


# Kullanıcının kullandığı ad -> sembol. Uzun adlar önce denenir (bkz.
# `varlik_tespit_et`): "çeyrek altın" ile "altın" aynı cümlede geçer ve
# spesifik olan kazanmalıdır.
#
# BIST hisseleri burada YOK: kodları zaten sembolün kendisiyle yazılıyor
# (THYAO) ve şirket adları `market_query` tarafında çözülüyor — oradaki
# `company_mappings.json` 126 yerli şirketi tanıyor.
#
# ABD hisseleri ise oraya girmiyor (RAG'da dokümanları yok) ve Türk kullanıcı
# bunları koduyla değil ADIYLA yazıyor: "apple hissesi ne kadar" cümlesinde
# `AAPL` geçmiyor. Bu yüzden yabancı şirket adları takma ad olarak buraya
# eklendi; sembolün kendisi zaten `_sembol_kumesi` taramasında bulunuyor.
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
    # ABD hisseleri — şirket adıyla.
    "apple": "AAPL",
    "microsoft": "MSFT",
    "nvidia": "NVDA",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "amazon": "AMZN",
    "meta platforms": "META",
    "facebook": "META",
    "tesla": "TSLA",
    "jpmorgan": "JPM",
    "jp morgan": "JPM",
    "visa": "V",
    "mastercard": "MA",
    "berkshire": "BRK-B",
    "berkshire hathaway": "BRK-B",
    "johnson": "JNJ",
    "eli lilly": "LLY",
    "lilly": "LLY",
    "unitedhealth": "UNH",
    "coca cola": "KO",
    "cocacola": "KO",
    "kola": "KO",
    "procter": "PG",
    "walmart": "WMT",
    "mcdonalds": "MCD",
    "mcdonald": "MCD",
    "exxon": "XOM",
    "caterpillar": "CAT",
}

# Fiyat/kur sorusunu ele veren kalıplar.
_FIYAT_KALIPLARI = (
    "ne kadar",
    "kac tl",
    "kac lira",
    "kac para",
    # ABD hisseleri evrene girince doğal soru hâline geldi ("AAPL kaç
    # dolar?"). Kalıbın kendisi `varlik_tespit_et` içinde metinden
    # SİLİNİYOR, aksi hâlde içindeki "dolar" USDTRY takma adına eşleşir ve
    # kullanıcı bir hisse sorarken cevaba kur da eklenirdi.
    "kac dolar",
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


# Küçültülünce gündelik Türkçeyle çakışan semboller: çıplak taramaya ham
# metinde BÜYÜK HARFİYLE girerler, küçük harfli hâlleriyle değil. Aynı çözüm
# `market_query.sirket_tespit_et` içinde MAVI/ESEN/EFOR için de kullanılıyor.
#
# `V` (Visa) tek harf — neredeyse her cümlede sahte eşleşme üretirdi.
# `META` finans Türkçesinde "emtia" anlamında kullanılır; "meta fiyatları
# arttı" cümlesi Meta Platforms sorgusu değildir.
#
# İkisi de takma adıyla ("visa", "meta platforms", "facebook") her yazımda
# bulunabildiği için kısıtlama erişimi kapatmıyor.
_BUYUK_HARF_SEMBOLLER = {"V", "META"}


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

    # "kaç dolar" bir FİYAT KALIBIDIR, varlık adı değil: içindeki "dolar"
    # takma ad taramasına girmemeli (bkz. `_FIYAT_KALIPLARI`). Kalıp
    # eşleşmesi `fiyat_niyeti` içinde ham `normalized` üzerinde yapıldığı
    # için burada silmek o tarafı etkilemiyor.
    normalized = normalized.replace("kac dolar", " ")

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
        if sembol in _BUYUK_HARF_SEMBOLLER:
            # Ham metinde, büyük harfiyle (bkz. `_BUYUK_HARF_SEMBOLLER`).
            eslesti = bool(re.search(rf"\b{re.escape(sembol)}\b", query))
        else:
            eslesti = bool(re.search(rf"\b{re.escape(_normalize(sembol))}\b", normalized))
        if eslesti and sembol not in bulunan:
            bulunan.append(sembol)

    return bulunan


# "son ay"/"son 3 ay"/"son bir yıl" gibi SABİT ifadeler _GECMIS_KALIPLARI'nda
# var ama araya bir SAYI giren biçimi ("son 1 ayda") hiçbiriyle eşleşmiyordu
# (ölçümle doğrulandı, 2026-08-26: "altın nasıl bir yükseklik gösterdi son 1
# ayda" RAG'a düşüp başarısız oluyordu, neredeyse aynı anlama gelen "altın
# yükseldi mi son bir ayda" ise "yükseldi" kalıbı üzerinden doğru şekilde
# fiyat geçmişi yoluna gidiyordu). Sabit ifadelere tek tek "son 1 ay", "son 2
# ay" ... eklemek yerine genel bir "son <sayı> gün/hafta/ay/yıl" kalıbı.
_SURE_KALIP_RE = re.compile(r"\bson\s+\d+\s+(gun|hafta|ay|yil)\w*")


def _icerir(normalized: str, kaliplar: tuple[str, ...]) -> bool:
    return any(k in normalized for k in kaliplar)


# Bir sorguda BIST ticker'ı ("ARCLK", "PGSUS", "KCHOL" gibi kodun kendisi —
# şirket adı değil) VE "ne kadar" gibi genel bir kalıp birlikte geçtiğinde,
# bu iki şart tek başına PİYASA FİYATI sorusu sanılıyordu (ölçümle
# doğrulandı, 2026-08-26): "ARCLK'nin serbest nakit akışı ne kadar?" ve
# "PGSUS'un brüt kârı ne kadar oldu?" gibi sorular — ikisi de RAG'daki
# bilanço dokümanlarında YANITI olan içerik soruları — fiyat/tarihçe
# tool'una yönlendirilip "kayıt bulunamadı" ya da alakasız güncel fiyat
# döndürüyordu. Sorguda bilinen bir bilanço/finansal-tablo kalemi geçiyorsa
# bu artık şirketin KENDİ PİYASA FİYATI değil, RAPORLANMIŞ bir rakam
# soruluyor demektir — fiyat_niyeti devre dışı kalır, RAG yoluna düşer.
_ICERIK_KELIMELERI_RE = re.compile(
    r"\b(net kar|brut kar|faaliyet kari|favok|ciro|hasilat|nakit akis|"
    r"temettu|marj|segment|ortaklik yapisi|sermaye artir|yonetim kurulu|"
    r"kurumsal olay|bilanco|gelir tablosu)\w*"
)


def fiyat_niyeti(query: str) -> dict | None:
    """Fiyat sorusuysa `{"symbols": [...], "history": bool}`, değilse None.

    İki şart birlikte aranır: SORU fiyat/kur soruyor OLMALI ve bir varlık
    ADIYLA anılmalı. Tek başına "ne kadar" bir portföy sorusu olabilir
    ("portföyüm ne kadar"), tek başına "dolar" ise haber sorusu olabilir
    ("dolar hakkında haberler"). İkisi birlikteyken niyet nettir.
    """
    normalized = _normalize(query)
    if _ICERIK_KELIMELERI_RE.search(normalized):
        return None

    semboller = varlik_tespit_et(query)
    if not semboller:
        return None

    gecmis = _icerir(normalized, _GECMIS_KALIPLARI) or bool(_SURE_KALIP_RE.search(normalized))
    if not gecmis and not _icerir(normalized, _FIYAT_KALIPLARI):
        return None

    return {"symbols": semboller, "history": gecmis}
