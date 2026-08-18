"""Piyasa Araştırma Ajanı'nın kullanacağı retrieval arayüzü.

Saf DB tabanlı RAG: LLM yanıt üretmez, internetten canlı veri çekmez.
`data/documents/` altına eklenen dokümanlar `rag.ingest` ile veritabanına
işlenir; burada yalnızca o veritabanı sorgulanır. Sorguya yeterince yakın bir
sonuç yoksa "bulunamadı" anlamına gelen boş liste döner — uydurma yok (AK 5.5).

Hibrit eşleştirme: yalnızca vektör mesafesi küçük veri setlerinde ve kısa
sorularda yanıltıcı olabiliyor (alakasız bir sorgu, gerçekten alakalı bir
sorgudan daha düşük mesafe alabiliyor — ölçümle doğrulandı). Bu yüzden bir
sonuç yalnızca hem mesafe eşiğini geçerse HEM DE sorguyla en az bir gerçek
kelime paylaşırsa "bulundu" sayılır."""

import re

from app.core.config import settings
from rag.vector_store import VectorStore, get_vector_store

NOT_FOUND_MESSAGE = "Veritabanımızda bu sorguyla ilgili doğrulanmış bir bilgi bulunamadı."

# Kelime örtüşmesi kontrolünde göz ardı edilecek, ayırt edici olmayan Türkçe
# kelimeler (aksansız/ASCII-katlanmış halleriyle — bkz. _normalize). Bunlar
# olmasaydı "ne kadar", "hakkında" gibi hemen her sorguda geçen kelimeler,
# alakasız dokümanlarla bile sahte örtüşme yaratırdı.
_STOPWORDS = {
    "ve",
    "veya",
    "ile",
    "bir",
    "bu",
    "su",
    "o",
    "de",
    "da",
    "mi",
    "mu",
    "midir",
    "ne",
    "kadar",
    "icin",
    "gibi",
    "cok",
    "az",
    "en",
    "daha",
    "olan",
    "olarak",
    "gore",
    "kac",
    "hangi",
    "nasil",
    "nedir",
    "hakkinda",
    "bilgi",
    "haber",
    "lutfen",
    "acaba",
    "son",
    "var",
    "yok",
}

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_MIN_KEYWORD_LEN = 3
_PREFIX_MATCH_LEN = (
    4  # Türkçe çekim ekleri için (şirket/şirketin gibi) tam eşleşme yerine önek karşılaştırması
)

# Chroma'dan çekilecek en az aday sayısı (top_k'dan bağımsız): ham vektör
# mesafesi doğru dokümanı her zaman ilk birkaç sıraya koymuyor (ölçümle
# doğrulandı), bu yüzden süzme daha geniş bir havuz üzerinde yapılır.
_MIN_CANDIDATE_POOL = 20

# Türkçe klavyesi olmayan / aksan girmeyen kullanıcılar için: "FAVOK" ile
# "FAVÖK", "sirket" ile "şirket" aynı kelime sayılsın diye ASCII'ye katlanır.
_TURKISH_FOLD_MAP = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u"})


def _normalize(text: str) -> str:
    return text.lower().translate(_TURKISH_FOLD_MAP)


def _keywords(text: str) -> set[str]:
    tokens = _WORD_RE.findall(_normalize(text))
    return {t for t in tokens if len(t) >= _MIN_KEYWORD_LEN and t not in _STOPWORDS}


# Bir sonucun "yeterince örtüşüyor" sayılması için sorgu kelimelerinin en az
# yarısından FAZLASININ eşleşmesi gerekir (tam yarısı yetmez — bkz. altta).
_MIN_KEYWORD_OVERLAP_RATIO = 0.5


def _query_keyword_matches(qk: str, candidate_keywords: set[str]) -> bool:
    prefix_len = min(len(qk), _PREFIX_MATCH_LEN)
    qk_prefix = qk[:prefix_len]
    return any(len(ck) >= prefix_len and ck[:prefix_len] == qk_prefix for ck in candidate_keywords)


def _shares_a_keyword(query_keywords: set[str], candidate_keywords: set[str]) -> bool:
    """Gerçek verideki iki bulgu: "hisse", "çeyrek", "net kâr" gibi finans
    jargonu neredeyse her dokümanda geçiyor. Tek bir ortak kelime yeterli
    sayılırsa (eski davranış) alakasız bir sorgu ("Bitcoin fiyatı ne kadar")
    salt "fiyat" kelimesi üzerinden bir analist raporuyla eşleşiyor; ya da iki
    şirketin de "ikinci çeyrek net kâr açıkladı" gibi neredeyse aynı kalıpla
    yazılmış bilançoları arasında, sorgudaki asıl şirket adı hiç eşleşmese
    bile jenerik kelimeler üzerinden yanlış şirket kapıdan geçebiliyor
    (ölçümle doğrulandı — gerçek THYAO/ASELSAN dokümanlarıyla test edildi).

    Bu yüzden "en az yarısından fazlası eşleşsin" kuralı var: `> 0.5`, `>= 0.5`
    değil — 2 kelimelik bir sorguda tek kelimenin (%50) eşleşmesi yetmemeli,
    ikisinin de eşleşmesi gerekir; bu da "Bitcoin fiyatı" gibi sorguları
    tek kelimeden (fiyat) geçirmeyi engeller."""
    if not query_keywords:
        return False
    matched = sum(1 for qk in query_keywords if _query_keyword_matches(qk, candidate_keywords))
    return matched / len(query_keywords) > _MIN_KEYWORD_OVERLAP_RATIO


def _result_keywords(result: dict) -> set[str]:
    text = result.get("content", "")
    metadata = result.get("metadata") or {}
    for key in ("baslik", "sirket", "tur", "kaynak"):
        value = metadata.get(key)
        if value:
            text = f"{text} {value}"
    return _keywords(text)


def _sirket_matches_query(result: dict, query_keywords: set[str]) -> bool:
    """İki farklı şirketin bilançosu neredeyse aynı jenerik kalıpla
    yazıldığında ("ikinci çeyrek net kâr açıklandı") ikisi de aynı kelime-
    örtüşme oranını alabiliyor (ölçümle doğrulandı: gerçek THYAO/ASELSAN
    dokümanlarıyla). Bu durumda, sonucun KENDİ `sirket` alanı sorgudaki
    kelimelerden biriyle eşleşiyorsa sıralamada öne alınır — jenerik içerik
    kelimeleri değil, dokümanın ait olduğu şirketin kendisi tercih sebebidir."""
    sirket = (result.get("metadata") or {}).get("sirket")
    if not sirket:
        return False
    sirket_keywords = _keywords(str(sirket))
    return any(_query_keyword_matches(qk, sirket_keywords) for qk in query_keywords)


def _build_where(
    sirket: str | None, donem: str | None, donem_listesi: list[str] | None, tur: str | None
) -> dict | None:
    """Chroma metadata filtresi üretir. Şirket/dönem/tür verilirse arama uzayı
    vektör benzerliği hesaplanmadan ÖNCE daraltılır — bu, benzerlik aramasının
    yapısal olarak yanlış şirket/dönem döndürmesini engeller (post-filter tek
    başına yeterli değil: ilk top_k sonucun tamamı yanlış şirketten gelebilir
    ve gerçek eşleşme hiç görünmeyebilir)."""
    if donem and donem_listesi:
        raise ValueError("donem ve donem_listesi birlikte verilemez")

    kosullar = []
    if sirket:
        kosullar.append({"sirket": sirket})
    if donem:
        kosullar.append({"donem": donem})
    if donem_listesi:
        kosullar.append({"donem": {"$in": donem_listesi}})
    if tur:
        kosullar.append({"tur": tur})

    if not kosullar:
        return None
    if len(kosullar) == 1:
        return kosullar[0]
    return {"$and": kosullar}


def _matches_filters(
    result: dict,
    sirket: str | None,
    donem: str | None,
    donem_listesi: list[str] | None,
    tur: str | None,
) -> bool:
    """Son filtre: Chroma'nın `where`'i doğru uyguladığını varsaymak yerine
    dönen sonucu istenen alanlara karşı tekrar doğrular (bkz. Market Research
    Ajanı tasarımındaki "son filtre" adımı — vektör aramasının yapısal olarak
    engelleyemediği yanılsamalara karşı ikinci bir savunma hattı)."""
    metadata = result.get("metadata") or {}
    if sirket and metadata.get("sirket") != sirket:
        return False
    if donem and metadata.get("donem") != donem:
        return False
    if donem_listesi and metadata.get("donem") not in donem_listesi:
        return False
    if tur and metadata.get("tur") != tur:
        return False
    return True


class Retriever:
    def __init__(self, store: VectorStore | None = None) -> None:
        self._store = store or get_vector_store()

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        *,
        sirket: str | None = None,
        donem: str | None = None,
        donem_listesi: list[str] | None = None,
        tur: str | None = None,
    ) -> list[dict[str, str]]:
        """Sorguya en yakın doküman parçalarını döndürür.

        `sirket`/`donem`/`donem_listesi`/`tur` verilirse deterministik
        filtre olarak uygulanır (hem arama uzayını daraltan ön filtre, hem
        dönen sonucu doğrulayan son filtre) — serbest metin benzerliğinin
        yanlış şirket/dönem döndürmesi yapısal olarak engellenir. Bu alanlar
        `None` bırakılırsa (bugünkü tek çağıran, search_market_news, hep
        böyle çağırır) davranış öncekiyle aynıdır: yalnızca serbest metin
        araması + mesafe/kelime örtüşmesi kontrolü.

        Bir sonuç ancak hem Chroma mesafesi `settings.rag_distance_threshold`
        altındaysa HEM DE sorguyla en az bir anlamlı kelime paylaşıyorsa (ya
        da yapılandırılmış filtrelerle geldiyse) döner. Hiçbiri sağlanmazsa
        boş liste döner."""
        query = query.strip()
        if not query:
            return []

        query_keywords = _keywords(query)
        if not query_keywords:
            return []

        # Chroma'dan istenen top_k'dan daha GENİŞ bir aday havuzu çekilir: ham
        # vektör mesafesi doğru dokümanı ilk top_k'ya sokmayabiliyor (ör. iki
        # şirketin bilançosu neredeyse aynı kalıpla yazıldığında yanlış şirket
        # mesafece daha yakın çıkabiliyor — ölçümle doğrulandı). Süzme
        # (mesafe eşiği + kelime örtüşmesi) bu geniş havuz üzerinde yapılır,
        # sonra çağıranın istediği top_k'ya kesilir.
        candidate_pool = max(top_k * 4, _MIN_CANDIDATE_POOL)
        where = _build_where(sirket, donem, donem_listesi, tur)
        results = self._store.similarity_search(query, top_k=candidate_pool, where=where)

        filtered = [
            r
            for r in results
            if r.get("distance", 1.0) <= settings.rag_distance_threshold
            and _shares_a_keyword(query_keywords, _result_keywords(r))
            and _matches_filters(r, sirket, donem, donem_listesi, tur)
        ]
        # Chroma zaten mesafeye göre sıralı döndürdüğü için stabil sort,
        # kendi şirketi sorguyla eşleşen sonuçları öne alırken aynı grup
        # içinde mesafe sırasını korur.
        filtered.sort(key=lambda r: not _sirket_matches_query(r, query_keywords))
        return filtered[:top_k]

    def answer(self, query: str, top_k: int | None = None) -> dict:
        """Doğrudan kullanım için: bul ya da 'bulunamadı' söyle. LLM'e ya da
        internete gitmez — yalnızca veritabanını kontrol eder."""
        results = self.retrieve(query, top_k=top_k or settings.rag_top_k)
        if not results:
            return {"found": False, "message": NOT_FOUND_MESSAGE, "results": []}
        return {"found": True, "message": None, "results": results}
