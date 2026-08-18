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
    "ve", "veya", "ile", "bir", "bu", "su", "o", "de", "da",
    "mi", "mu", "midir",
    "ne", "kadar", "icin", "gibi", "cok", "az", "en", "daha",
    "olan", "olarak", "gore", "kac", "hangi", "nasil", "nedir",
    "hakkinda", "bilgi", "haber", "lutfen", "acaba", "son", "var", "yok",
}

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_MIN_KEYWORD_LEN = 3
_PREFIX_MATCH_LEN = 4  # Türkçe çekim ekleri için (şirket/şirketin gibi) tam eşleşme yerine önek karşılaştırması

# Türkçe klavyesi olmayan / aksan girmeyen kullanıcılar için: "FAVOK" ile
# "FAVÖK", "sirket" ile "şirket" aynı kelime sayılsın diye ASCII'ye katlanır.
_TURKISH_FOLD_MAP = str.maketrans(
    {"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u"}
)


def _normalize(text: str) -> str:
    return text.lower().translate(_TURKISH_FOLD_MAP)


def _keywords(text: str) -> set[str]:
    tokens = _WORD_RE.findall(_normalize(text))
    return {t for t in tokens if len(t) >= _MIN_KEYWORD_LEN and t not in _STOPWORDS}


def _shares_a_keyword(query_keywords: set[str], candidate_keywords: set[str]) -> bool:
    for qk in query_keywords:
        prefix_len = min(len(qk), _PREFIX_MATCH_LEN)
        qk_prefix = qk[:prefix_len]
        for ck in candidate_keywords:
            if len(ck) >= prefix_len and ck[:prefix_len] == qk_prefix:
                return True
    return False


def _result_keywords(result: dict) -> set[str]:
    text = result.get("content", "")
    metadata = result.get("metadata") or {}
    for key in ("baslik", "sirket", "tur", "kaynak"):
        value = metadata.get(key)
        if value:
            text = f"{text} {value}"
    return _keywords(text)


class Retriever:
    def __init__(self, store: VectorStore | None = None) -> None:
        self._store = store or get_vector_store()

    def retrieve(self, query: str, top_k: int = 5) -> list[dict[str, str]]:
        """Sorguya en yakın doküman parçalarını döndürür. Bir sonuç ancak hem
        Chroma mesafesi `settings.rag_distance_threshold` altındaysa HEM DE
        sorguyla en az bir anlamlı kelime paylaşıyorsa döner. İkisi de
        sağlanmazsa boş liste döner."""
        query = query.strip()
        if not query:
            return []

        query_keywords = _keywords(query)
        if not query_keywords:
            return []

        results = self._store.similarity_search(query, top_k=top_k)
        return [
            r
            for r in results
            if r.get("distance", 1.0) <= settings.rag_distance_threshold
            and _shares_a_keyword(query_keywords, _result_keywords(r))
        ]

    def answer(self, query: str, top_k: int | None = None) -> dict:
        """Doğrudan kullanım için: bul ya da 'bulunamadı' söyle. LLM'e ya da
        internete gitmez — yalnızca veritabanını kontrol eder."""
        results = self.retrieve(query, top_k=top_k or settings.rag_top_k)
        if not results:
            return {"found": False, "message": NOT_FOUND_MESSAGE, "results": []}
        return {"found": True, "message": None, "results": results}
