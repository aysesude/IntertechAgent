"""Piyasa Araştırma Ajanı'nın kullanacağı retrieval arayüzü.
TODO: gerçek sorgu genişletme / yeniden sıralama mantığı henüz uygulanmadı."""

from rag.vector_store import VectorStore, get_vector_store


class Retriever:
    def __init__(self, store: VectorStore | None = None) -> None:
        self._store = store or get_vector_store()

    def retrieve(self, query: str, top_k: int = 5) -> list[dict[str, str]]:
        raise NotImplementedError("TODO: RAG retrieval henüz uygulanmadı")
