"""Chroma sağlayıcı katmanının hata sözleşmesi.

`docs/MCP-TOOLS.md` §2: dış kaynak yanıt vermiyorsa zarfta PROVIDER_UNAVAILABLE
görünmeli. Bunu tool değil sağlayıcı katmanı belirler — tool'un chromadb'nin
istisna tiplerini tanıması gerekmesin diye. Testler gerçek Chroma/embedding
modeli olmadan koşar: `_collection` bir `cached_property`, örnek sözlüğüne
sahte bir koleksiyon konarak devre dışı bırakılır.
"""

import pytest

from app.core.exceptions import NotFoundError, ProviderUnavailableError
from rag.vector_store import ChromaVectorStore


class _PatlayanKoleksiyon:
    """chromadb'nin bağlantı koptuğunda yaptığını taklit eder."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def count(self):
        raise self._exc

    def upsert(self, **kwargs):
        raise self._exc


def _store_with_collection(collection) -> ChromaVectorStore:
    store = ChromaVectorStore(host="chroma", port=8000)
    # cached_property değerini örnek sözlüğüne koymak, gerçek bağlantı kurma
    # yolunu hiç çalıştırmadan koleksiyonu yerine geçirir.
    store.__dict__["_collection"] = collection
    return store


def test_similarity_search_chroma_hatasini_provider_unavailable_yapar():
    store = _store_with_collection(_PatlayanKoleksiyon(ConnectionError("connection refused")))

    with pytest.raises(ProviderUnavailableError) as exc_info:
        store.similarity_search("enflasyon")

    # İç metin teknik ayrıntıyı taşır (yalnızca loga gider, zarfa değil).
    assert "chroma:8000" in str(exc_info.value)


def test_add_documents_chroma_hatasini_provider_unavailable_yapar():
    store = _store_with_collection(_PatlayanKoleksiyon(TimeoutError("read timeout")))

    with pytest.raises(ProviderUnavailableError):
        store.add_documents(documents=["metin"], metadatas=[{"baslik": "x"}])


def test_kendi_app_error_imiz_saglayici_hatasi_kiligina_girmez():
    """`_provider_errors` yalnızca dış kaynak hatalarını çevirir; kendi
    `AppError`'ımız olduğu gibi geçer, yoksa kod hatamız "kaynak erişilemiyor"
    diye raporlanır ve yanlış yerde aranır."""
    store = _store_with_collection(_PatlayanKoleksiyon(NotFoundError("collection missing")))

    with pytest.raises(NotFoundError):
        store.similarity_search("enflasyon")


def test_bos_koleksiyonda_arama_hata_degil_bos_liste():
    class _BosKoleksiyon:
        def count(self):
            return 0

    store = _store_with_collection(_BosKoleksiyon())

    assert store.similarity_search("enflasyon") == []


def test_mutlu_yol_sonuclari_dogru_esler():
    """Hata sarmalayıcısı eklenirken bozulmadığının kanıtı: dolu bir
    koleksiyonda arama, Chroma'nın üç paralel listesini (documents/metadatas/
    distances) tek tek sözlüklere doğru sırayla eşlemeye devam eder."""

    class _DoluKoleksiyon:
        def count(self):
            return 2

        def query(self, query_texts, n_results, where=None):
            assert n_results == 2  # top_k, koleksiyon boyutuyla sınırlanır
            return {
                "documents": [["Örnek Şirket net kârı arttı.", "Alakasız metin."]],
                "metadatas": [[{"baslik": "bilanço"}, {"baslik": "başka"}]],
                "distances": [[0.20, 0.95]],
            }

    store = _store_with_collection(_DoluKoleksiyon())

    results = store.similarity_search("Örnek Şirket net kârı", top_k=5)

    assert [r["content"] for r in results] == [
        "Örnek Şirket net kârı arttı.",
        "Alakasız metin.",
    ]
    assert [r["metadata"]["baslik"] for r in results] == ["bilanço", "başka"]
    assert [r["distance"] for r in results] == [0.20, 0.95]


def test_where_filtresi_chroma_query_cagrisina_gecirilir():
    """rag/retriever.py'nin deterministik ön filtresi buradan Chroma'ya gider."""

    class _KaydedenKoleksiyon:
        def count(self):
            return 1

        def query(self, query_texts, n_results, where=None):
            self.son_where = where
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    koleksiyon = _KaydedenKoleksiyon()
    store = _store_with_collection(koleksiyon)

    store.similarity_search("enflasyon", where={"sirket": "ASELS"})

    assert koleksiyon.son_where == {"sirket": "ASELS"}


def test_clear_koleksiyonu_siler_ve_cache_i_temizler():
    """`add_documents` yalnızca upsert yapar; data/documents/'dan kaldırılan
    bir dosyanın parçaları temizlenmeden kalıcı olarak birikir (production'da
    ölçümle doğrulandı). `clear()` bunu önler: koleksiyonu silip cached_property
    önbelleğini boşaltır ki sonraki erişim koleksiyonu boş yeniden kursun."""

    class _SahteClient:
        def __init__(self) -> None:
            self.cagrilar: list[tuple[str, str]] = []

        def get_or_create_collection(self, name, **kwargs):
            self.cagrilar.append(("get_or_create", name))
            return object()

        def delete_collection(self, name):
            self.cagrilar.append(("delete", name))

    store = ChromaVectorStore(host="chroma", port=8000, collection_name="financial_documents")
    sahte_client = _SahteClient()
    store.__dict__["_client"] = sahte_client
    store.__dict__["_collection"] = object()  # onceden erisilmis gibi davran

    store.clear()

    assert sahte_client.cagrilar == [
        ("get_or_create", "financial_documents"),
        ("delete", "financial_documents"),
    ]
    assert "_collection" not in store.__dict__


def test_clear_chroma_hatasini_provider_unavailable_yapar():
    class _PatlayanClient:
        def get_or_create_collection(self, name, **kwargs):
            raise ConnectionError("connection refused")

    store = ChromaVectorStore(host="chroma", port=8000)
    store.__dict__["_client"] = _PatlayanClient()

    with pytest.raises(ProviderUnavailableError):
        store.clear()
