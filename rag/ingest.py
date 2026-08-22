"""Doküman yükleme: data/documents/ altındaki markdown dosyalarını okur,
front matter'ı metadata'ya çevirir ve vektör veritabanına işler.

Çalıştırma:
    docker compose exec -w / api python -m rag.ingest

Tekrar çalıştırılabilir (idempotent): her çalıştırma önce koleksiyonu
temizler, sonra data/documents/'daki dosyalardan yeniden yükler. Chroma
her zaman bu klasörün birebir yansımasıdır — kaldırılan bir dosyanın ya
da eski bir parçalama ayarının (chunk_size/overlap) izi kalmaz. Yalnızca
upsert yapan bir önceki sürüm, silinen dosyaların parçalarını kalıcı
olarak biriktiriyordu (production'da ölçümle doğrulandı).

Doküman formatı için bkz. data/documents/README.md
"""

import logging
import sys
from pathlib import Path

import yaml
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.exceptions import ProviderUnavailableError

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DOCUMENTS_DIR = Path("/data/documents")

# Front matter: dosyanın başındaki --- ile çevrili YAML bloğu.
_FRONT_MATTER_SINIRI = "---"


def _chroma_deger(v: object) -> str | int | float | bool:
    """Chroma metadata değerleri yalnızca str/int/float/bool kabul eder.
    `datetime.date` gibi (YAML'ın `tarih: 2026-07-28` satırından ürettiği)
    diğer tipler metne çevrilir; str/int/float/bool olduğu gibi kalır — bool'u
    string'e çevirmek "true" filtresinin "True" metniyle eşleşmemesine yol
    açar (bkz. rag/retriever.py `where` filtresi)."""
    if v is None:
        return ""
    if isinstance(v, str | int | float | bool):
        return v
    return str(v)


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

    temiz_metadata = {k: _chroma_deger(v) for k, v in metadata.items()}
    temiz_metadata["dosya"] = path.name

    eksik = [alan for alan in ("baslik", "tarih", "tur") if not temiz_metadata.get(alan)]
    if eksik:
        logger.warning("%s: zorunlu alan(lar) eksik: %s", path.name, ", ".join(eksik))

    # Bilanço/finansal sonuç dokümanları sayısal değer taşır; hangi çeyreğe ve
    # solo/konsolide hangi tabloya ait olduğu belirsizse "dönem karıştırma"
    # riskini deterministik filtrelerle kapatamayız (bkz. rag/retriever.py).
    if temiz_metadata.get("tur") == "bilanco":
        bilanco_eksik = [
            alan for alan in ("donem", "konsolide_mi") if temiz_metadata.get(alan, "") == ""
        ]
        if bilanco_eksik:
            logger.warning(
                "%s: tur=bilanco için zorunlu alan(lar) eksik: %s",
                path.name,
                ", ".join(bilanco_eksik),
            )

    return Document(page_content=content, metadata=temiz_metadata)


def _bilanco_revizyonlarini_coz(documents: list[Document]) -> list[Document] | None:
    """Aynı (şirket, dönem) için birden fazla `bilanco` dokümanı olabilir —
    şirket düzeltilmiş rakamlarla yeniden yayımlarsa (restatement). `revize_no`
    (belirtilmezse 1 varsayılır) hangisinin güncel olduğunu belirler; yalnızca
    en yüksek revize_no'ya sahip doküman(lar) vektör veritabanına işlenir,
    eskisi sessizce dışlanır.

    Bu kontrol olmadan iki dokümanın parçaları Chroma'da kalıcı olarak yan
    yana durur (`ChromaVectorStore._make_id` metadata+içerik hash'lediği için
    ikisi de benzersiz kabul edilir, biri diğerinin üzerine yazmaz) ve sorgu
    anında hangisinin döneceği belirsiz kalır — çelişkili rakamlar sessizce
    karışabilir.

    Aynı revize_no ile çelişen birden fazla doküman bulunursa (kazara
    eklenmiş bir kopya olabilir, hangisinin doğru olduğu belirsiz) None
    döner; çağıran taraf bunu hata sayıp ingest'i durdurmalı."""
    gruplar: dict[tuple[str, str], list[Document]] = {}
    for doc in documents:
        if doc.metadata.get("tur") != "bilanco":
            continue
        anahtar = (doc.metadata.get("sirket", ""), doc.metadata.get("donem", ""))
        gruplar.setdefault(anahtar, []).append(doc)

    disarida_birakilan_dosyalar: set[str] = set()
    for (sirket, donem), grup in gruplar.items():
        if len(grup) < 2:
            continue
        revizeli = [(int(d.metadata.get("revize_no") or 1), d) for d in grup]
        max_revize = max(r for r, _ in revizeli)
        guncel_olanlar = [d for r, d in revizeli if r == max_revize]
        if len(guncel_olanlar) > 1:
            logger.error(
                "%s / %s için birden fazla bilanco dokümanı aynı revize_no (%d) "
                "ile bulundu: %s. Hangisinin güncel olduğu belirsiz — "
                "düzeltilmiş dokümana `revize_no` alanını bir üst değerle ekleyin.",
                sirket,
                donem,
                max_revize,
                ", ".join(d.metadata["dosya"] for d in guncel_olanlar),
            )
            return None
        for revize_no, d in revizeli:
            if revize_no < max_revize:
                disarida_birakilan_dosyalar.add(d.metadata["dosya"])
                logger.info(
                    "%s: %s / %s için daha eski revizyon (revize_no=%d < %d), "
                    "vektör veritabanına işlenmiyor.",
                    d.metadata["dosya"],
                    sirket,
                    donem,
                    revize_no,
                    max_revize,
                )

    if not disarida_birakilan_dosyalar:
        return documents
    return [d for d in documents if d.metadata["dosya"] not in disarida_birakilan_dosyalar]


def main() -> int:
    if not DOCUMENTS_DIR.exists():
        logger.error("Doküman klasörü bulunamadı: %s", DOCUMENTS_DIR)
        return 1

    dosyalar = sorted(p for p in DOCUMENTS_DIR.glob("*.md") if p.name.lower() not in {"readme.md"})

    if not dosyalar:
        # Bilinçli olarak 0 dönüyoruz: doküman eklenmemiş olması bir HATA değil,
        # yalnızca yapılacak iş olmaması. Bu ayrım kritik — deploy script'i artık
        # hataları `|| true` ile yutmak zorunda değil, dolayısıyla gerçek bir
        # ingest çökmesi deploy'u kırar ve görünür olur.
        logger.warning(
            "İşlenecek doküman yok, atlanıyor. data/documents/ klasörüne .md "
            "dosyaları ekleyin (format için o klasördeki README.md dosyasına bakın)."
        )
        return 0

    logger.info("%d dosya bulundu.", len(dosyalar))

    documents = [doc for path in dosyalar if (doc := _parse_document(path)) is not None]

    if not documents:
        logger.error("Hiçbir dosya ayrıştırılamadı.")
        return 1

    cozulmus_documents = _bilanco_revizyonlarini_coz(documents)
    if cozulmus_documents is None:
        return 1
    documents = cozulmus_documents

    # chunk_overlap=0: parçalar arası üst üste binme, sınırdaki bir başlığın
    # (ör. "## Not") hem bir önceki hem bir sonraki parçada aynen tekrar
    # etmesine yol açıyordu — ikisi de sonuca girip art arda eklenince aynı
    # başlık iki kez görünüyordu (ölçümle doğrulandı).
    #
    # chunk_size=500 -> 800: 500 çoğu paragrafı ortasından kesiyordu (ör. bir
    # THYAO paragrafı "...artan yakıt" diye bitip devamı ["maliyetleri
    # arttı"] ayrı bir parçaya düşüyordu; o parça sorguyla tek başına yeterli
    # kelime örtüşmesi sağlamadığı için sonuca hiç girmiyor, cevap yarım
    # cümleyle bitiyordu — ölçümle doğrulandı). 800, bu projedeki dokümanların
    # tek paragraflarının büyük çoğunluğunu bölmeden içine alıyor.
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=0)
    chunks = splitter.split_documents(documents)
    if not chunks:
        logger.error("Dokümanlar parçalanamadı.")
        return 1

    # Import burada: embedding modelinin yüklenmesi birkaç saniye sürüyor,
    # dosya doğrulaması başarısızsa boşuna beklemeyelim.
    from rag.vector_store import get_vector_store

    logger.info("%d parça vektör veritabanına işleniyor...", len(chunks))
    store = get_vector_store()
    try:
        # Önce temizlenir: yalnızca upsert yapmak, data/documents/'dan
        # kaldırılan dosyaların veya eski chunk_size/overlap ayarıyla
        # üretilmiş parçaların kalıcı olarak birikmesine yol açıyordu.
        store.clear()
        store.add_documents(
            documents=[c.page_content for c in chunks],
            metadatas=[c.metadata for c in chunks],
        )
    except ProviderUnavailableError as exc:
        # Traceback yerine ne yapılacağını söyleyen tek satır: bu komutu
        # çalıştıran kişi çoğu zaman chroma servisini başlatmayı unutmuş oluyor.
        logger.error(
            "Vektör veritabanına bağlanılamadı (%s). `docker compose up -d chroma` "
            "ile servisi başlatın ve .env dosyanızda CHROMA_HOST/CHROMA_PORT "
            "değerlerini kontrol edin.",
            exc.message,
        )
        return 1

    logger.info("Bitti. Toplam parça sayısı: %d", len(chunks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
