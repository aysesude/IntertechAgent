"""Finansal haber/rapor dokümanlarını (data/documents/) parçalayıp
vektör DB'ye yazan pipeline. TODO: chunking + embedding henüz uygulanmadı."""

from pathlib import Path

from rag.vector_store import VectorStore, get_vector_store


def load_documents(documents_dir: Path) -> list[str]:
    raise NotImplementedError("TODO: data/documents/ altındaki dosyaları okuyup metne çevir")


def chunk_document(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    raise NotImplementedError("TODO: chunking stratejisi belirlenmedi")


def ingest_all(documents_dir: Path, store: VectorStore | None = None) -> None:
    store = store or get_vector_store()
    raise NotImplementedError("TODO: load -> chunk -> add_documents akışı henüz uygulanmadı")
