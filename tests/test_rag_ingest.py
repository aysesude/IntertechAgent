"""`rag.ingest`'in restatement/versiyon çözümleme mantığı.

Bir şirket aynı çeyreği düzeltilmiş rakamlarla yeniden yayımlarsa (restatement),
`_bilanco_revizyonlarini_coz` yalnızca en yüksek `revize_no`'ya sahip dokümanı
tutmalı — aksi halde iki dokümanın parçaları Chroma'da kalıcı olarak yan yana
durur ve sorgu anında hangisinin döneceği belirsiz kalır (bkz. rag/ingest.py
docstring'i)."""

from langchain_core.documents import Document

from rag.ingest import _bilanco_revizyonlarini_coz


def _bilanco(dosya: str, sirket: str, donem: str, revize_no: int | None = None) -> Document:
    metadata = {"tur": "bilanco", "sirket": sirket, "donem": donem, "dosya": dosya}
    if revize_no is not None:
        metadata["revize_no"] = revize_no
    return Document(page_content="içerik", metadata=metadata)


def test_tekil_bilanco_dokumani_degismeden_doner():
    docs = [_bilanco("a.md", "ASELS", "2026-Q2")]

    sonuc = _bilanco_revizyonlarini_coz(docs)

    assert sonuc == docs


def test_farkli_sirket_veya_donem_birbirini_etkilemez():
    docs = [
        _bilanco("aselsan.md", "ASELS", "2026-Q2"),
        _bilanco("thy.md", "THYAO", "2026-Q2"),
        _bilanco("aselsan-eski.md", "ASELS", "2026-Q1"),
    ]

    sonuc = _bilanco_revizyonlarini_coz(docs)

    assert sonuc == docs


def test_bilanco_olmayan_dokumanlar_kontrole_dahil_edilmez():
    docs = [
        Document(
            page_content="x",
            metadata={
                "tur": "sirket_profili",
                "sirket": "ASELS",
                "donem": "2026-Q2",
                "dosya": "a.md",
            },
        ),
        Document(
            page_content="y",
            metadata={
                "tur": "sirket_profili",
                "sirket": "ASELS",
                "donem": "2026-Q2",
                "dosya": "b.md",
            },
        ),
    ]

    sonuc = _bilanco_revizyonlarini_coz(docs)

    assert sonuc == docs


def test_yuksek_revize_no_kazanir_eskisi_disarida_birakilir():
    eski = _bilanco("2026-08-05_ASELS_2ceyrek-bilanco.md", "ASELS", "2026-Q2", revize_no=1)
    yeni = _bilanco("2026-08-20_ASELS_2ceyrek-bilanco-duzeltme.md", "ASELS", "2026-Q2", revize_no=2)

    sonuc = _bilanco_revizyonlarini_coz([eski, yeni])

    assert sonuc == [yeni]


def test_revize_no_belirtilmeyen_dokuman_bir_sayilir():
    # revize_no verilmemişse 1 varsayılır — açıkça revize_no=2 verilen
    # düzeltme onu geçersiz kılmalı.
    eski = _bilanco("eski.md", "KRDMD", "2026-Q2")
    yeni = _bilanco("yeni.md", "KRDMD", "2026-Q2", revize_no=2)

    sonuc = _bilanco_revizyonlarini_coz([eski, yeni])

    assert sonuc == [yeni]


def test_ayni_revize_no_ile_celisen_iki_dokuman_none_doner():
    # Kazara eklenmiş bir kopya olabilir — hangisinin doğru olduğu
    # belirsiz, ingest bunu durdurup insan müdahalesi istemeli.
    a = _bilanco("a.md", "MGROS", "2026-Q2", revize_no=1)
    b = _bilanco("b.md", "MGROS", "2026-Q2", revize_no=1)

    sonuc = _bilanco_revizyonlarini_coz([a, b])

    assert sonuc is None


def test_uc_revizyon_arasindan_en_yuksegi_secilir():
    r1 = _bilanco("r1.md", "TUPRS", "2026-Q2", revize_no=1)
    r2 = _bilanco("r2.md", "TUPRS", "2026-Q2", revize_no=2)
    r3 = _bilanco("r3.md", "TUPRS", "2026-Q2", revize_no=3)

    sonuc = _bilanco_revizyonlarini_coz([r1, r2, r3])

    assert sonuc == [r3]
