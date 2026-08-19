"""Vektör DB soyutlaması. Şu an Chroma kullanıyoruz; ileride Qdrant'a geçerken
sadece burada yeni bir implementasyon eklenecek, çağıran kod değişmeyecek."""

import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from functools import cached_property
from typing import Any

from app.core.config import settings
from app.core.exceptions import AppError, ProviderUnavailableError


@contextmanager
def _provider_errors(operation: str, target: str) -> Iterator[None]:
    """Chroma'dan gelen her hatayı `ProviderUnavailableError`'a çevirir.

    Sözleşme (docs/MCP-TOOLS.md §2) "dış kaynak yanıt vermiyor" durumunu
    PROVIDER_UNAVAILABLE olarak zarfa yazmayı şart koşuyor ve ajanın bu kodda
    zarif düşüş yapmasını bekliyor. Bunu tool'un istisna tiplerini tek tek
    tanıması değil, sağlayıcı katmanının doğru istisnayı fırlatması sağlar:
    `@tool_handler` `AppError` türevlerini otomatik eşliyor.

    Yalnızca chromadb çağrılarını saran bloklarda kullanılır; kendi
    `AppError`'larımız olduğu gibi geçer ki kod hatamız "kaynak erişilemiyor"
    kılığına girmesin.
    """
    try:
        yield
    except AppError:
        raise
    except Exception as exc:
        raise ProviderUnavailableError(f"Chroma {operation} failed at {target}: {exc}") from exc


class VectorStore(ABC):
    @abstractmethod
    def add_documents(self, documents: list[str], metadatas: list[dict[str, Any]]) -> None:
        """Doküman parçalarını (chunk) embedding'leriyle birlikte saklar."""

    @abstractmethod
    def clear(self) -> None:
        """Koleksiyondaki tüm parçaları siler.

        `add_documents` yalnızca upsert yapar — bir kaynak dosya silinirse
        veya parçalama stratejisi (chunk_size/overlap) değişirse eski
        parçalar kendiliğinden silinmez, kalıcı olarak birikir (ölçümle
        doğrulandı: `data/documents/`'dan kaldırılan bir dosyanın parçaları
        production Chroma'da aylarca kalabilir). `rag.ingest` bu yüzden her
        çalıştığında önce `clear()` çağırır, sonra mevcut dosyalardan
        yeniden yükler — Chroma her zaman `data/documents/`'ın birebir
        yansıması olur, sapma birikmez."""

    @abstractmethod
    def similarity_search(
        self, query: str, top_k: int = 5, where: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Sorguya en yakın doküman parçalarını döndürür.

        `where` verilirse (Chroma metadata filtre sözdizimi), arama uzayı
        vektör benzerliği hesaplanmadan ÖNCE bu filtreyle daraltılır —
        benzerlik aramasının yapısal olarak dönem/şirket karıştırmasını
        önlemesi için (bkz. rag/retriever.py ön filtre)."""


class ChromaVectorStore(VectorStore):
    """`chroma` container'ına (docker-compose) HTTP üzerinden bağlanan, salt
    getirme (retrieval) yapan istemci. Yanıt üretimi burada yok — üretim/LLM
    katmanı bu sınıfı çağıran taraftadır, bu sınıf değildir."""

    def __init__(
        self,
        host: str = settings.chroma_host,
        port: int = settings.chroma_port,
        collection_name: str = settings.chroma_collection,
        embedding_model: str = settings.rag_embedding_model,
    ) -> None:
        self._host = host
        self._port = port
        self._collection_name = collection_name
        self._embedding_model = embedding_model

    # Bağlantı ilk kullanımda kurulur: import anında Chroma container'ı ayakta
    # olmayabilir. `clear()` sonrası sıfırlanır ki bir sonraki erişim
    # koleksiyonu yeniden (boş) oluştursun.
    @cached_property
    def _client(self):
        import chromadb

        with _provider_errors("connection", self._target):
            return chromadb.HttpClient(host=self._host, port=self._port)

    @cached_property
    def _collection(self):
        from chromadb.utils import embedding_functions

        # Hata durumunda cached_property değeri saklamaz; sonraki çağrı yeniden
        # dener. Chroma geç ayağa kalktıysa süreç yeniden başlatılmadan toparlar.
        with _provider_errors("connection", self._target):
            embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=self._embedding_model
            )
            return self._client.get_or_create_collection(
                name=self._collection_name,
                embedding_function=embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )

    def clear(self) -> None:
        with _provider_errors("clear", self._target):
            # Önce var olduğundan emin olunur (idempotent) ki delete_collection
            # "koleksiyon yok" durumunu bağlantı hatasıyla karıştırmasın.
            self._client.get_or_create_collection(self._collection_name)
            self._client.delete_collection(self._collection_name)
        self.__dict__.pop("_collection", None)

    @property
    def _target(self) -> str:
        """Log ve istisna metni için bağlantı adresi. Kullanıcıya gitmez."""
        return f"{self._host}:{self._port}"

    @staticmethod
    def _make_id(document: str, metadata: dict[str, Any]) -> str:
        """Aynı içerik + metadata her zaman aynı id'yi üretir, böylece
        `upsert` yeniden çalıştırmada kopya değil güncelleme yapar (idempotent)."""
        meta_repr = json.dumps(metadata, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(f"{meta_repr}::{document}".encode()).hexdigest()

    def add_documents(self, documents: list[str], metadatas: list[dict[str, Any]]) -> None:
        if not documents:
            return
        ids = [self._make_id(doc, meta) for doc, meta in zip(documents, metadatas)]
        with _provider_errors("upsert", self._target):
            self._collection.upsert(documents=documents, metadatas=metadatas, ids=ids)

    def similarity_search(
        self, query: str, top_k: int = 5, where: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        with _provider_errors("query", self._target):
            count = self._collection.count()
            if count == 0:
                return []

            result = self._collection.query(
                query_texts=[query], n_results=min(top_k, count), where=where or None
            )
        docs = result.get("documents") or [[]]
        metadatas = result.get("metadatas") or [[]]
        distances = result.get("distances") or [[]]

        return [
            {"content": doc, "metadata": meta or {}, "distance": distance}
            for doc, meta, distance in zip(docs[0], metadatas[0], distances[0])
        ]


def get_vector_store() -> VectorStore:
    return ChromaVectorStore()
