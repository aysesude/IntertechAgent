"""Doküman yükleme: data/documents/ altındaki markdown dosyalarını okur,
front matter'ı metadata'ya çevirir ve vektör veritabanına işler.

Çalıştırma:
    docker compose exec -w / api python -m rag.ingest

Tekrar çalıştırılabilir (idempotent): pipeline aynı içerikli parçaları
atladığı için mevcut dokümanlar yeniden yüklenmez.

Doküman formatı için bkz. data/documents/README.md
"""

import logging
import sys
from pathlib import Path

import yaml
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DOCUMENTS_DIR = Path("/data/documents")

# Front matter: dosyanın başındaki --- ile çevrili YAML bloğu.
_FRONT_MATTER_SINIRI = "---"


def _parse_document(path: Path) -> Document | None:
    """Bir markdown dosyasını front matter + içerik olarak ayrıştırır."""
    raw = path.read_text(encoding="utf-8")

    if not raw.startswith(_FRONT_MATTER_SINIRI):
        logger.warning("%s: front matter yok, atlanıyor", path.name)
        return None

    parts = raw.split(_FRONT_MATTER_SINIRI, 2)
    if len(parts) < 3:
        logger.warning("%s: front matter kapatılmamış, atlanıyor", path.name)
        return None

    try:
        metadata = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:
        logger.warning("%s: front matter okunamadı (%s), atlanıyor", path.name, exc)
        return None

    content = parts[2].strip()
    if not content:
        logger.warning("%s: içerik boş, atlanıyor", path.name)
        return None

    # Chroma metadata değerleri yalnızca basit tip kabul eder, bu yüzden hepsini
    # metne çeviriyoruz.
    #
    # `tarih: 2026-07-28` gibi bir satırı YAML otomatik olarak `datetime.date`
    # nesnesine çeviriyor. Önceki sürüm yalnızca str/int/float/bool kabul ettiği
    # için tarih alanı sessizce düşüyor ve "zorunlu alan eksik" uyarısı çıkıyordu.
    temiz_metadata = {k: ("" if v is None else str(v)) for k, v in metadata.items()}
    temiz_metadata["dosya"] = path.name

    eksik = [
        alan for alan in ("baslik", "tarih", "tur") if not temiz_metadata.get(alan)
    ]
    if eksik:
        logger.warning("%s: zorunlu alan(lar) eksik: %s", path.name, ", ".join(eksik))

    return Document(page_content=content, metadata=temiz_metadata)


def main() -> int:
    if not DOCUMENTS_DIR.exists():
        logger.error("Doküman klasörü bulunamadı: %s", DOCUMENTS_DIR)
        return 1

    dosyalar = sorted(
        p for p in DOCUMENTS_DIR.glob("*.md") if p.name.lower() not in {"readme.md"}
    )

    if not dosyalar:
        logger.error(
            "İşlenecek doküman yok. data/documents/ klasörüne .md dosyaları ekleyin "
            "(format için o klasördeki README.md dosyasına bakın)."
        )
        return 1

    logger.info("%d dosya bulundu.", len(dosyalar))

    documents = [doc for path in dosyalar if (doc := _parse_document(path)) is not None]

    if not documents:
        logger.error("Hiçbir dosya ayrıştırılamadı.")
        return 1

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_documents(documents)
    if not chunks:
        logger.error("Dokümanlar parçalanamadı.")
        return 1

    # Import burada: embedding modelinin yüklenmesi birkaç saniye sürüyor,
    # dosya doğrulaması başarısızsa boşuna beklemeyelim.
    from rag.vector_store import get_vector_store

    logger.info("%d parça vektör veritabanına işleniyor...", len(chunks))
    store = get_vector_store()
    store.add_documents(
        documents=[c.page_content for c in chunks],
        metadatas=[c.metadata for c in chunks],
    )

    logger.info("Bitti. Toplam parça sayısı: %d", len(chunks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
