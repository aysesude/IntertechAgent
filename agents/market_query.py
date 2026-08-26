"""Kullanıcının serbest metin piyasa sorusundan deterministik filtre çıkarımı.

Neden gerekli: `rag/retriever.py` `sirket`/`donem`/`tur` filtrelerini destekliyor
ve bunlar arama uzayını vektör benzerliği hesaplanmadan ÖNCE daraltıyor. Filtre
verilmezse doğru dokümanın aday havuzuna hiç girmeme ihtimali kalıyor —
retriever'daki kelime-örtüşme koruması yalnızca sonradan eleme yapabiliyor.
Bu modül o filtreleri sorgudan çıkarır.

Tasarım kuralı — **eksik bilgiyi varsayımla doldurma** (CLAUDE.md "Uydurmama"):
yıl açıkça yazılmamışsa `donem` üretilmez. "Son çeyrek nasıldı" sorusunda bugünün
tarihinden çeyrek tahmin etmek, yanlış tahminde kullanıcıya "bilgi bulunamadı"
dedirtir — oysa doğru doküman veritabanında durmaktadır. Belirsizlikte filtre
koymamak, yanlış filtre koymaktan iyidir: serbest metin araması yine çalışır.

LLM kullanılmaz; tamamen kural tabanlıdır, dolayısıyla test edilebilir ve
deterministiktir.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

# Konteynerde `agents/` kök dizine, `data/` de kök dizine bağlanıyor
# (bkz. rag/ingest.py'deki `/data/documents`); lokalde ise ikisi de depo
# kökünün altında. `parents[1]` her iki durumda da doğru yeri gösterir.
_MAPPINGS_PATH = Path(__file__).resolve().parents[1] / "data" / "company_mappings.json"

# Türkçe karakterleri ASCII'ye katlar. rag/retriever.py ile AYNI eşleme —
# "şirket"/"sirket" iki katmanda farklı normalleşirse filtre ile arama
# birbirini tutmaz.
_TURKISH_FOLD_MAP = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u"})

_ORDINAL_CEYREKLER = {
    "ilk": 1,
    "birinci": 1,
    "ikinci": 2,
    "ucuncu": 3,
    "dorduncu": 4,
}

_YIL_RE = re.compile(r"\b(20\d{2})\b")

# "2. çeyrek", "2.çeyrek", "2 ceyrek"
_RAKAM_CEYREK_RE = re.compile(r"\b([1-4])\s*\.?\s*ceyre")
# "birinci çeyrek", "ikinci çeyrek"
_YAZI_CEYREK_RE = re.compile(r"\b(ilk|birinci|ikinci|ucuncu|dorduncu)\s+ceyre")
# "Q2", "2Ç" (çeyrek ASCII katlamasından sonra "c" olur)
_KISA_CEYREK_RE = re.compile(r"\bq([1-4])\b|\b([1-4])c\b")


def _normalize(text: str) -> str:
    return text.lower().translate(_TURKISH_FOLD_MAP)


@lru_cache(maxsize=1)
def _sirket_eslemesi() -> dict[str, str]:
    """`{normalize edilmiş ad: borsa kodu}`. Dosya okuması bir kez yapılır.

    Dosya yoksa boş sözlük döner: şirket tespiti devre dışı kalır, arama
    serbest metinle çalışmaya devam eder. Eksik bir eşleme dosyası yüzünden
    tüm piyasa sorgularının çökmesi, filtresiz aramadan kötüdür.
    """
    try:
        ham = json.loads(_MAPPINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {_normalize(ad): kayit["ticker"] for ad, kayit in ham.items() if kayit.get("ticker")}


def _tum_sirketleri_tespit_et(query: str) -> set[str]:
    """Sorguda geçen TÜM farklı şirketlerin borsa kodlarını döndürür.

    Kelime sınırı (`\\b`) aranır — aksi hâlde "thy" gibi kısa kodlar başka
    kelimelerin içinde sahte eşleşme üretir.
    """
    eslemeler = _sirket_eslemesi()
    bulunanlar: set[str] = set()

    # 1) BÜYÜK HARF ticker taraması — küçültmeden ÖNCE.
    #
    # Bazı borsa kodları gündelik Türkçe kelimelerle çakışıyor: MAVI (renk),
    # ESEN, EFOR, BERA. Hepsi küçültülüp eşleştirildiğinde "grafikteki mavi
    # çizgi" sorgusu Mavi Giyim'e gidiyordu (ölçüldü). Kodlar teamülen BÜYÜK
    # yazıldığı için büyük harf duyarlı bir tarama ikisini ayırıyor: "MAVI"
    # şirkettir, "mavi" renktir.
    #
    # Yalnızca tickerın kendisi aranır, ad varyantları değil — "Mavi Giyim"
    # zaten aşağıdaki normal taramada bulunuyor.
    for ticker in set(eslemeler.values()):
        if re.search(rf"\b{re.escape(ticker)}\b", query):
            bulunanlar.add(ticker)

    # 2) Normal tarama: küçültülmüş ve aksansız.
    normalized = _normalize(query)
    for ad, ticker in eslemeler.items():
        if re.search(rf"\b{re.escape(ad)}\b", normalized):
            bulunanlar.add(ticker)

    return bulunanlar


def sirket_tespit_et(query: str) -> str | None:
    """Sorguda geçen TEK şirketin borsa kodunu döndürür ("ASELS"); sorguda
    hiç şirket geçmiyorsa veya BİRDEN FAZLA FARKLI şirket geçiyorsa None
    döner.

    İki-şirketli sorgularda filtre KONULMAMALI: "Tüpraş'ın tam sahipliği ne
    zaman Koç Holding'e geçti" gibi bir M&A/ortaklık sorusu hem TUPRS hem
    KCHOL'ü doğal olarak barındırır. Eskiden en uzun eşleşen ad (burada
    "Koç Holding") kazanıp filtreyi TEK şirkete daraltıyordu — soru asıl
    Tüpraş hakkında olsa bile arama KCHOL dokümanlarıyla sınırlanıp doğru
    cevap (TUPRS profilindeki "Kurumsal olaylar tarihçesi" bölümü) aday
    havuzuna hiç girmiyordu (ölçüldü, 2026-08-26). Modülün kendi tasarım
    kuralı zaten bunu söylüyor: belirsizlikte filtre koymamak yanlış filtre
    koymaktan iyidir — serbest metin araması iki şirketi de bulur (bkz.
    modül başlığı).

    NOT: bu fonksiyon "arama filtresi" ihtiyacı için TEK/None döner. "Sorguda
    HERHANGİ bir şirket geçiyor mu?" sorusu için (ör. scope_checker'ın
    kapsam-dışı-etiket istisnası) `sirket_gecer_mi()` kullanılmalı — o,
    birden fazla şirket geçse bile True döner (bkz. o fonksiyonun docstring'i).
    """
    bulunanlar = _tum_sirketleri_tespit_et(query)
    if len(bulunanlar) == 1:
        return next(iter(bulunanlar))
    return None


def sirket_sayisi(query: str) -> int:
    """Sorguda geçen FARKLI şirket sayısını döndürür.

    Çoklu şirket karşılaştırma sorgularında ("Akbank, İş Bankası ve Yapı
    Kredi'nin ... karşılaştır") sabit `top_k=5` yetersiz kalıyordu: korpus
    büyüdükçe (kurumsal olaylar/nakit akış içeriği eklendikçe) her şirketin
    kendi ilgili chunk'ı için rekabet arttı, 3 şirketten biri (ör. Yapı
    Kredi) üst-5'in dışına düşüp sorgunun cevabından tamamen kayboluyordu
    (ölçümle doğrulandı, 2026-08-26). market_agent bu sayıyı kullanarak
    top_k'yı şirket sayısına göre genişletir.
    """
    return len(_tum_sirketleri_tespit_et(query))


def sirket_gecer_mi(query: str) -> bool:
    """Sorguda bilinen bir BIST şirketi (adıyla ya da koduyla) geçiyor mu?

    `sirket_tespit_et`'ten farkı: o, TEK bir filtre üretebilmek için birden
    fazla şirket geçtiğinde None döner (bkz. docstring'i). Ama scope_checker
    gibi "en az bir şirket adı geçiyorsa kapsam-dışı-etiket istisnası
    uygulanır" mantığı için bu ayrım YANLIŞ: "Akbank, İş Bankası ve Yapı
    Kredi'nin ... karşılaştır" gibi 3 şirketli bir sorguda "Yapı Kredi"
    bankacılık-ürünleri sınıfındaki "kredi" etiketiyle çakışıp sorguyu
    OUT_OF_SCOPE'a düşürüyordu — `sirket_tespit_et` üç şirket birden
    geçtiği için None dönüyor, istisna hiç tetiklenmiyordu (ölçüldü,
    2026-08-26, analist canlı test turu; bu, çoklu-şirket None davranışının
    scope_checker'a sızan bir yan etkisiydi). Bu fonksiyon şirket SAYISINA
    bakmaz, yalnızca en az bir tane geçip geçmediğine bakar.
    """
    return bool(_tum_sirketleri_tespit_et(query))


def donem_tespit_et(query: str) -> str | None:
    """Sorgudan "2026-Q2" biçiminde dönem üretir; üretemezse None.

    Hem çeyrek HEM yıl açıkça yazılmış olmalı. Yıl yoksa None döner — bkz.
    modül başlığındaki "eksik bilgiyi varsayımla doldurma" kuralı.
    """
    normalized = _normalize(query)

    ceyrek: int | None = None
    if m := _RAKAM_CEYREK_RE.search(normalized):
        ceyrek = int(m.group(1))
    elif m := _YAZI_CEYREK_RE.search(normalized):
        ceyrek = _ORDINAL_CEYREKLER[m.group(1)]
    elif m := _KISA_CEYREK_RE.search(normalized):
        ceyrek = int(m.group(1) or m.group(2))

    if ceyrek is None:
        return None

    yil = _YIL_RE.search(normalized)
    if not yil:
        return None

    return f"{yil.group(1)}-Q{ceyrek}"


def filtre_cikar(query: str) -> dict[str, str]:
    """Tool'a geçirilecek filtreleri toplar. Boş değerler hiç eklenmez, böylece
    çağıran taraf `**filtreler` ile doğrudan açabilir."""
    filtreler: dict[str, str] = {}
    if sirket := sirket_tespit_et(query):
        filtreler["sirket"] = sirket
    if donem := donem_tespit_et(query):
        filtreler["donem"] = donem
    return filtreler


# Sorgunun ARŞİV değil GÜNCELLİK istediğini işaretleyen kelimeler. Kelime
# sınırıyla aranır (`\b`) — aksi hâlde "sonuç" içindeki "son" gibi sahte
# eşleşmeler olur.
#
# "haber" de güncellik sayılır: "ASELSAN haberleri neler" sorusu "son"
# demeden de bugünü kastediyor. Bu kelime olmadan soru yalnızca arşive
# gidiyor ve şirketin o günkü bildirimi hiç görünmüyordu (ölçüldü).
# Gövde olarak yazıldı ("haberleri", "haberi" de eşleşsin).
_GUNCELLIK_KELIMELERI_RE = re.compile(r"\b(son|guncel|bugun|simdi|dun|yeni|haber\w*)\b")


def guncellik_istegi_var_mi(query: str) -> bool:
    """Sorgu, arşivde henüz olmayabilecek GÜNCEL bir bilgi mi istiyor?

    Canlı KAP çağrısı (`get_live_kap_disclosures`) her piyasa sorusunda
    tetiklenmez — 60 saniyeye kadar sürebilen bir dış istektir ve çoğu soru
    zaten RAG'daki arşiv belgeleriyle (bilanço metni, şirket profili) tam
    cevaplanır. Bu fonksiyon, sorgunun güncellik ipucu taşıyıp taşımadığını
    işaretler; taşımıyorsa canlı çağrı hiç yapılmaz.

    Kasıtlı olarak kaba bir sezgi: yanlış negatif (güncellik istendiği hâlde
    tetiklenmemek) sessiz bir eksiklik, yanlış pozitif ise en kötü ihtimalle
    gereksiz bir dış istek — ikincisi daha ucuz bir hata, bu yüzden eşik
    düşük tutuldu.
    """
    return bool(_GUNCELLIK_KELIMELERI_RE.search(_normalize(query)))


# Sorgunun GENEL piyasa gündemini istediğini işaretleyen kelimeler. Kelime
# sınırıyla aranır; "haberler" gibi çekimli hâlleri yakalamak için gövde
# olarak yazıldı ("haber" -> "haberler", "haberi").
_GUNDEM_KELIMELERI_RE = re.compile(r"\b(haber\w*|gundem\w*|piyasa\w*|borsa\w*|ekonomi\w*)\b")


def genel_gundem_istegi_var_mi(query: str) -> bool:
    """Sorgu, ŞİRKETSİZ bir genel piyasa gündemi mi istiyor?

    İki koşul birlikte aranır (çağıran tarafta): gündem kelimesi VAR ve
    şirket tespit edilMEmiş. Şirket adı geçen bir soruda ("ASELSAN haberleri
    neler") gündem bloğu eklenmez — kullanıcı o şirketi sordu, karşılığı
    KAP bildirimleridir; genel gündem başlıkları alakasız gürültü olurdu.

    Güncellik şartı burada AYRICA aranmaz: "piyasa haberleri neler" cümlesi
    "son" demeden de bugünü kastediyor. Arşivde haber tutmadığımız için bu
    soruların tek karşılığı zaten canlı gündem.
    """
    return bool(_GUNDEM_KELIMELERI_RE.search(_normalize(query)))
