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


def sirket_tespit_et(query: str) -> str | None:
    """Sorguda geçen ilk şirketin borsa kodunu döndürür ("ASELS"), yoksa None.

    Uzun adlar önce denenir: "garanti bankası" ile "garan" aynı sorguda
    eşleşebilir, uzun olan daha spesifik olduğu için öncelikli. Kelime sınırı
    (`\\b`) aranır — aksi hâlde "thy" gibi kısa kodlar başka kelimelerin
    içinde sahte eşleşme üretir.
    """
    normalized = _normalize(query)
    eslemeler = _sirket_eslemesi()
    for ad in sorted(eslemeler, key=len, reverse=True):
        if re.search(rf"\b{re.escape(ad)}\b", normalized):
            return eslemeler[ad]
    return None


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
