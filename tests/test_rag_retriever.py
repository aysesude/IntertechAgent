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

    def clear(self) -> None:
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


def test_retrieve_serbest_metinde_yanlis_sirket_tamamen_elenir():
    """sirket= parametresi verilmeden (serbest metin yolu — bugünkü tek
    çağıran search_market_news hep böyle çağırır), iki şirketin bilançosu
    aynı jenerik kalıpla yazıldığında ikisi de kelime-örtüşme eşiğini
    geçebiliyor (ölçümle doğrulandı: gerçek ASELS/THYAO dokümanlarıyla).
    Sonuçlardan biri sorgudaki şirketle eşleştiyse, başka bir şirkete
    etiketli sonuçlar sıralamada geriye atılmakla kalmaz, tamamen elenir."""
    store = _FakeVectorStore(
        [
            _doc("ASELSAN ikinci çeyrek net kâr açıkladı", sirket="ASELS", distance=0.3),
            _doc("THYAO ikinci çeyrek net kâr açıkladı", sirket="THYAO", distance=0.2),
            _doc("Piyasada ikinci çeyrek net kâr haberleri", sirket="", distance=0.4),
        ]
    )
    retriever = Retriever(store=store)

    results = retriever.retrieve("ASELSAN ikinci çeyrek net kârı")

    sirketler = {r["metadata"]["sirket"] for r in results}
    assert "THYAO" not in sirketler
    assert "ASELS" in sirketler
    assert "" in sirketler  # etiketsiz genel haber elenmez


def test_retrieve_sirket_eslesmesi_yoksa_hicbir_sey_elenmez():
    """Sorgu belirli bir şirkete işaret etmiyorsa (ör. sektör geneli bir
    soru), farklı şirketlerin sonuçları bir arada kalabilir — eleme yalnızca
    sonuçlardan biri gerçekten sorgudaki şirketle eşleştiğinde devreye girer."""
    store = _FakeVectorStore(
        [
            _doc("ASELS bilançosu net kâr açıklandı", sirket="ASELS", distance=0.3),
            _doc("THYAO bilançosu net kâr açıklandı", sirket="THYAO", distance=0.4),
        ]
    )
    retriever = Retriever(store=store)

    results = retriever.retrieve("bilanço net kâr açıklamaları")

    assert {r["metadata"]["sirket"] for r in results} == {"ASELS", "THYAO"}
