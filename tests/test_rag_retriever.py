import pytest

from rag.retriever import Retriever
from rag.vector_store import VectorStore


class _FakeVectorStore(VectorStore):
    """Gercek Chroma/embedding olmadan Retriever'in filtre mantigini test eder."""

    def __init__(self, documents: list[dict]) -> None:
        self._documents = documents
        self.son_where: dict | None = None

    def add_documents(self, documents, metadatas) -> None:
        raise NotImplementedError

    def similarity_search(self, query: str, top_k: int = 5, where: dict | None = None):
        self.son_where = where
        return self._documents


def _doc(content: str, distance: float = 0.1, **metadata) -> dict:
    return {"content": content, "metadata": metadata, "distance": distance}


def test_retrieve_sirket_filtresi_where_olarak_gecirilir():
    store = _FakeVectorStore([_doc("ASELS bilançosu net kâr açıklandı", sirket="ASELS")])
    retriever = Retriever(store=store)

    retriever.retrieve("ASELS bilanço", sirket="ASELS")

    assert store.son_where == {"sirket": "ASELS"}


def test_retrieve_coklu_filtre_and_ile_birlestirilir():
    store = _FakeVectorStore([])
    retriever = Retriever(store=store)

    retriever.retrieve("bilanço sorgusu", sirket="ASELS", donem="2026-Q2", tur="bilanco")

    assert store.son_where == {
        "$and": [{"sirket": "ASELS"}, {"donem": "2026-Q2"}, {"tur": "bilanco"}]
    }


def test_retrieve_filtresiz_where_gonderilmez():
    store = _FakeVectorStore([_doc("ASELS hakkında genel bilgi", sirket="ASELS")])
    retriever = Retriever(store=store)

    results = retriever.retrieve("ASELS genel bilgi")

    assert store.son_where is None
    assert len(results) == 1


def test_retrieve_son_filtre_yanlis_sirketi_eler():
    # Chroma'nin where filtresi bir sekilde yanlis calissa bile (ya da hic
    # verilmese bile) son filtre yanlis sirketi elemeli — bu, "vektor
    # aramasinin yapisal olarak sirket karistirmasini engellemeli" ilkesinin
    # ikinci savunma hatti.
    store = _FakeVectorStore(
        [
            _doc("ASELS bilançosu net kâr açıklandı", sirket="ASELS"),
            _doc("THYAO bilançosu net kâr açıklandı", sirket="THYAO"),
        ]
    )
    retriever = Retriever(store=store)

    results = retriever.retrieve("net kâr bilanço", sirket="ASELS")

    assert len(results) == 1
    assert results[0]["metadata"]["sirket"] == "ASELS"


def test_retrieve_donem_listesi_ile_son_ceyrekler_filtrelenir():
    store = _FakeVectorStore(
        [
            _doc("ASELS 2026 Ç2 bilançosu net kâr açıklandı", sirket="ASELS", donem="2026-Q2"),
            _doc("ASELS 2025 Ç1 bilançosu net kâr açıklandı", sirket="ASELS", donem="2025-Q1"),
        ]
    )
    retriever = Retriever(store=store)

    results = retriever.retrieve(
        "net kâr bilanço", sirket="ASELS", donem_listesi=["2026-Q1", "2026-Q2"]
    )

    assert len(results) == 1
    assert results[0]["metadata"]["donem"] == "2026-Q2"


def test_retrieve_donem_ve_donem_listesi_birlikte_verilemez():
    store = _FakeVectorStore([])
    retriever = Retriever(store=store)

    with pytest.raises(ValueError):
        retriever.retrieve("soru", donem="2026-Q2", donem_listesi=["2026-Q1", "2026-Q2"])
