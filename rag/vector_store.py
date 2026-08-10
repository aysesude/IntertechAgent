"""Vektör DB soyutlaması. Şu an Chroma kullanıyoruz; ileride Qdrant'a geçerken
sadece burada yeni bir implementasyon eklenecek, çağıran kod değişmeyecek."""

from abc import ABC, abstractmethod
from typing import Any

from app.core.config import settings


class VectorStore(ABC):
    @abstractmethod
    def add_documents(self, documents: list[str], metadatas: list[dict[str, Any]]) -> None:
        """Doküman parçalarını (chunk) embedding'leriyle birlikte saklar."""

    @abstractmethod
    def similarity_search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Sorguya en yakın doküman parçalarını döndürür."""


class ChromaVectorStore(VectorStore):
    """TODO: gerçek chunking/embedding pipeline'ı (rag/ingest.py, rag/retriever.py)
    tamamlanana kadar bu implementasyon boş kalacak."""

    def __init__(self, host: str = settings.chroma_host, port: int = settings.chroma_port,
                 collection_name: str = settings.chroma_collection) -> None:
        self._host = host
        self._port = port
        self._collection_name = collection_name

    def add_documents(self, documents: list[str], metadatas: list[dict[str, Any]]) -> None:
        raise NotImplementedError("TODO: RAG ingest pipeline'ı henüz uygulanmadı")

    def similarity_search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        raise NotImplementedError("TODO: RAG retrieval henüz uygulanmadı")


def get_vector_store() -> VectorStore:
    return ChromaVectorStore()
