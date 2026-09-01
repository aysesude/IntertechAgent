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
    # Endeksler. Fiyatları `price_history`'de duruyor ve Piyasa şeridinde
    # gösteriliyor ama satın alınamıyorlar (`tradable=False`), dolayısıyla
    # `_sembol_kumesi`nin varsayılan süzgecine takılıyorlardı. Ölçüldü
    # (1 Eylül 2026): "BIST bugün nasıl?" ve "S&P 500 ne durumda?" belge
    # aramasına düşüp "doğrulanmış bilgi bulunamadı" cevabı alıyordu —
    # aynı oturumda Analist Ajanı XU100 serisini sorunsuz kullanırken.
    "bist": "XU100",
    "bist 100": "XU100",
    "bist100": "XU100",
    "borsa istanbul": "XU100",
    "s&p": "SPX",
    "s&p 500": "SPX",
    "sp 500": "SPX",
    "sp500": "SPX",
    # Fon türleri. Kullanıcı fon KODUNU değil TÜRÜNÜ yazıyor ("serbest fon
    # alabilir miyim"); her türün evrende tek temsilcisi var, dolayısıyla
    # eşleme tek anlamlı.
    "serbest fon": "BHE",
    "para piyasasi fonu": "IOO",
    "eurobond fonu": "AKE",
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
    # Endekslerin doğal soru biçimi. "kac tl" endekse uymuyor (puan cinsinden
    # kote edilir) ve kullanıcı "BIST bugün nasıl?" diye soruyor. İçerik
    # soruları (bilanço, ciro, temettü...) `_ICERIK_KELIMELERI_RE` ile zaten
    # bu yoldan önce eleniyor, dolayısıyla "X'in 2. çeyreği nasıl" buraya
    # düşmüyor.
    "ne durumda",
    "kac puan",
    "bugun nasil",
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


# Satın alınamayan ama FİYATI SORULABİLEN semboller. `tradable=False` bir
# alım-satım kısıtıdır, fiyat sorgusu kısıtı değil: endeksin kaç puan olduğu
# meşru bir sorudur ve verisi elimizde.
#
# BRENT bilerek DIŞARIDA: `agents/scope.yaml` petrolü `emtia_diger` altında
# kapsam dışı sayıyor, oysa Piyasa şeridinde gösteriliyor. Bu bir tutarsızlık
# ve çözümü bir ürün kararı — kapsam içiyse buraya eklenir, değilse şeritten
# çıkarılır. Karar verilmeden tek taraflı açmak, kapsam kuralını koddan
# sessizce ezmek olurdu.
_FIYATLANAN_ALINAMAYAN = {"XU100", "SPX"}


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
        if (a.tradable or a.symbol in _FIYATLANAN_ALINAMAYAN)
        and a.symbol not in _BELIRSIZ_SEMBOLLER
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


# Sorguda geçen ZAMAN PENCERESİ -> TimeWindow değeri.
#
# Uzun kalıplar önce denenir: "son 12 ay" hem "son 12 ay" hem "son ay" ile
# eşleşir, spesifik olan kazanmalıdır.
#
# Ölçülen hata (1 Eylül 2026): "Dolar son bir yılda ne yaptı?" sorusu
# `get_asset_price_history`'ye pencere GEÇİRMEDEN gidiyordu; tool varsayılanı
# 3 ay olduğu için cevap *"son bir yıllık performansı bulunmuyor"* deyip 3
# aylık veriyi veriyordu. Bir yıllık seri veritabanında duruyordu; sorulan
# soru cevaplanmamıştı.
_PENCERE_KALIPLARI: tuple[tuple[str, str], ...] = (
    ("yilbasindan", "ytd"),
    ("yil basindan", "ytd"),
    ("bu yil", "ytd"),
    ("son 12 ay", "12m"),
    ("son bir yil", "12m"),
    ("son 1 yil", "12m"),
    ("gecen yil", "12m"),
    ("son yil", "12m"),
    ("son 6 ay", "6m"),
    ("son alti ay", "6m"),
    ("son 3 ay", "3m"),
    ("son uc ay", "3m"),
    ("son ceyrek", "3m"),
    ("son 1 ay", "1m"),
    ("son bir ay", "1m"),
    ("gecen ay", "1m"),
    ("son ay", "1m"),
    ("son hafta", "1m"),
    ("gecen hafta", "1m"),
)

# Pencere anlaşılamazsa tool'un kendi varsayılanı kullanılır; burada bir
# tahmin üretilmez.
VARSAYILAN_PENCERE = "3m"


def pencere_cikar(query: str) -> str | None:
    """Sorguda geçen zaman penceresini `TimeWindow` değeri olarak döndürür.

    Hiçbir kalıp eşleşmezse `None` — çağıran taraf tool varsayılanına bırakır.
    "Son 2 ay"/"son 9 ay" gibi ara değerler en yakın ÜST pencereye yuvarlanır
    (`_SURE_KALIP_RE` yolu): kullanıcının istediğinden kısa bir pencere
    göstermek, sorulan soruyu cevaplamamak olur.
    """
    normalized = _normalize(query)
    for kalip, pencere in _PENCERE_KALIPLARI:
        if kalip in normalized:
            return pencere

    eslesme = _SURE_KALIP_RE.search(normalized)
    if eslesme is None:
        return None

    sayi = int(re.search(r"\d+", eslesme.group(0)).group(0))
    birim = eslesme.group(1)
    if birim.startswith("yil"):
        return "12m"
    if birim.startswith("gun") or birim.startswith("hafta"):
        return "1m"
    # Ay: en yakın ÜST pencere.
    for esik, pencere in ((1, "1m"), (3, "3m"), (6, "6m")):
        if sayi <= esik:
            return pencere
    return "12m"


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
    r"kurumsal olay|bilanco|gelir tablosu|hedef fiyat|hedef kapanis|"
    r"analist tavsiye|analist tahmin)\w*"
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

    return {
        "symbols": semboller,
        "history": gecmis,
        # Yalnızca geçmiş sorgusunda anlamlı; güncel fiyatta pencere yok.
        "window": pencere_cikar(query) if gecmis else None,
    }


# "GARAN'ın hedef fiyatı ne?", "ASELS için analist tavsiyesi ne?" gibi
# sorular — bir analist tarafından GEÇMİŞTE raporlanmış bir rakam, GÜNCEL
# piyasa fiyatı DEĞİL (bkz. _ICERIK_KELIMELERI_RE'deki "hedef fiyat" bloğu:
# fiyat_niyeti() bunları kendi kapsamına almıyor, market_agent bu fonksiyonu
# fiyat_niyeti'nden ÖNCE kontrol eder).
_HEDEF_FIYAT_KALIPLARI = (
    "hedef fiyat",
    "hedef kapanis",
    "analist tavsiye",
    "analist hedef",
    "analist tahmin",
)


# "Aselsan'ın F/K oranı kaç?", "Akbank'ın PD/DD'si nedir?" — bir şirketin
# DEĞERLEME ÇARPANLARI. Hedef fiyat gibi bu da RAG dokümanlarında değil,
# `get_fundamentals` tool'unda (yfinance) yaşayan ayrı bir veri sınıfı.
#
# Ölçüldü (1 Eylül 2026 sohbet turu): doğrudan sorulduğunda soru Piyasa
# Ajanı'na düşüyor ve o ajanın böyle bir tool'u olmadığı için *"elimdeki
# belgelerde yer almıyor"* deniyordu; iki soru sonra aynı oturumda Analist
# Ajanı aynı şirketin F/K'sını veriyordu. Aynı soruya iki farklı cevap, tek
# bir hatadan daha çok güven kaybettirir.
_TEMEL_ORAN_KALIPLARI = (
    "f/k",
    "fk orani",
    "fiyat kazanc",
    "pd/dd",
    "pddd",
    "pd dd",
    "piyasa degeri defter",
    "favok marj",
    "kar marji",
    "temettu verimi",
    "temel analiz",
    "degerleme carpan",
    "carpanlari",
)


# "Serbest fon alabilir miyim?", "BIST 100'den alabilir miyim?" — kullanıcı
# fiyat değil, KENDİ ERİŞİMİNİ soruyor. Cevabı sistemin kendi verisinde:
# varlığın uygunluk seviyesi (`advice_eligibility`) ile kullanıcının anket
# puanı, ayrıca `tradable` bayrağı.
#
# Ölçüldü (1 Eylül 2026): iki soru da Web Araştırma Ajanı'na düşüp
# ansiklopedik bir cevap aldı ("nitelikli yatırımcı statüsüne bağlıdır"),
# oysa doğru cevap elimizde: puan 6, serbest fon seviye 7 — alamaz.
_UYGUNLUK_KALIPLARI = (
    "alabilir miyim",
    "alabilir miyiz",
    "alabiliyor muyum",
    "alim yapabilir miyim",
    "yatirim yapabilir miyim",
    "erisebilir miyim",
    "bana uygun mu",
    "benim icin uygun mu",
)


def uygunluk_niyeti(query: str) -> str | None:
    """Sorgu "bunu alabilir miyim" tipindeyse hedef varlığın sembolünü
    döndürür, değilse None.

    Varlık tespit edilemezse None — "fon alabilir miyim" gibi genel bir soru
    hangi fonu kastettiğini söylemiyor ve uydurma bir sembol seçmek yanlış
    cevap üretirdi; o durumda soru normal akışta kalır.
    """
    normalized = _normalize(query)
    if not any(k in normalized for k in _UYGUNLUK_KALIPLARI):
        return None

    semboller = varlik_tespit_et(query)
    return semboller[0] if len(semboller) == 1 else None


def temel_oran_niyeti(query: str) -> str | None:
    """Sorgu bir şirketin değerleme çarpanlarını soruyorsa o şirketin
    ticker'ını döndürür, değilse None.

    `hedef_fiyat_niyeti` ile aynı kalıp: kalıp geçse bile şirket tespit
    edilemezse None döner ("F/K oranı nasıl hesaplanır" bir KAVRAM sorusudur,
    Web Araştırma Ajanı'na aittir) — uydurma şirket varsayılmaz.
    """
    normalized = _normalize(query)
    if not any(k in normalized for k in _TEMEL_ORAN_KALIPLARI):
        return None

    from agents.market_query import sirket_tespit_et

    return sirket_tespit_et(query)


def hedef_fiyat_niyeti(query: str) -> str | None:
    """Sorgu hedef fiyat/analist tavsiyesi soruyorsa tespit edilen TEK BIST
    şirketinin ticker'ını döndürür, değilse None.

    Şirket tespiti `market_query.sirket_tespit_et` ile yapılır (BIST ticker/
    şirket adı eşlemesi — `varlik_tespit_et`'in kapsadığı döviz/emtia/yabancı
    hisse takma adlarından farklı bir küme). Kalıp geçse bile şirket
    tespit edilemezse (ör. "hedef fiyatlar nasıl belirlenir" gibi genel bir
    kavram sorusu) None döner — RAG/kavram yoluna bırakılır, uydurma şirket
    varsayılmaz.
    """
    normalized = _normalize(query)
    if not any(k in normalized for k in _HEDEF_FIYAT_KALIPLARI):
        return None

    from agents.market_query import sirket_tespit_et

    return sirket_tespit_et(query)
