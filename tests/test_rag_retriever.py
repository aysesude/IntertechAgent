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


def test_retrieve_buyuk_i_harfi_kelimeyi_parcalamaz():
    """str.lower() Türkçe büyük "İ" harfini "i" + birleşen nokta işaretine
    çevirir; bu, \\w+ regex'inin kelimeyi ("BİM" -> "bi"+"m" gibi) anlamsız
    parçalara bölmesine yol açıyordu ve şirket adı sorgudan tamamen
    düşüyordu (bkz. rag/retriever.py _normalize). Bu test "İ" içeren bir
    şirket adının hâlâ geçerli bir arama kelimesi olarak tanınmasını
    doğrular."""
    store = _FakeVectorStore(
        [
            _doc("BİM Birleşik Mağazalar hedef fiyat açıklandı", sirket="BIMAS", distance=0.3),
            _doc(
                "THYAO için bilanço sonrası hedef fiyat açıklandı",
                sirket="THYAO",
                distance=0.1,
            ),
        ]
    )
    retriever = Retriever(store=store)

    results = retriever.retrieve("BİM hedef fiyat")

    sirketler = {r["metadata"]["sirket"] for r in results}
    assert "THYAO" not in sirketler
    assert "BIMAS" in sirketler


def test_retrieve_yalnizca_jenerik_kelimelerle_eslesme_reddedilir():
    """Uydurma/alakasız bir şirket adı + genel finans kelimeleri içeren bir
    sorgu ("xyzabc uydurma bir şirketin hisse fiyatı ne kadar" gibi), hiçbir
    gerçek şirket/konu adı eşleşmese bile salt "hisse"/"fiyat"/"şirket" gibi
    klişelerin üçü tesadüfen tek bir dokümanda birlikte geçtiği için oran
    barajını (>0.5) geçebiliyordu (ölçümle doğrulandı: gerçek THYAO analist
    raporuyla). Bu test, yalnızca jenerik klişelerle örtüşen bir sonucun artık
    reddedildiğini doğrular — eşleşen kelimelerden en az biri klişe dışı
    olmalı."""
    store = _FakeVectorStore(
        [
            _doc(
                "Şirket ikinci çeyrek net kâr açıkladı. Hedef fiyatlar hakkında "
                "hissesinde analist görüşleri farklılaştı.",
                sirket="THYAO",
                distance=0.3,
            )
        ]
    )
    retriever = Retriever(store=store)

    results = retriever.retrieve("xyzabc uydurma bir şirketin hisse fiyatı ne kadar")

    assert results == []


def test_retrieve_jenerik_olmayan_eslesme_varsa_kabul_edilir():
    """Yukarıdaki kısıtlama gerçek eşleşmeleri kırmamalı: sorgu jenerik
    kelimelerin yanında en az bir belirgin (şirket adı gibi) kelime de
    içeriyorsa sonuç yine dönmeli."""
    store = _FakeVectorStore(
        [
            _doc(
                "THYAO ikinci çeyrek bilançosu sonrası hedef fiyat açıklandı",
                sirket="THYAO",
                distance=0.3,
            )
        ]
    )
    retriever = Retriever(store=store)

    results = retriever.retrieve("THYAO hedef fiyatı ne kadar")

    assert len(results) == 1
    assert results[0]["metadata"]["sirket"] == "THYAO"


def test_retrieve_takma_ad_ile_baska_sirketler_elenir():
    """AKBNK ticker kodu foldlanınca "akbnk" olur, "Akbank" kelimesi ise
    "akbank" — ilk 4 harf ("akbn" vs "akba") örtüşmüyor. Bu yüzden salt
    ticker koduna dayanan önek karşılaştırması, kullanıcı günlük şirket
    adını yazdığında hiç tetiklenmiyor ve "başka şirketi tamamen ele"
    güvenlik ağı devreye girmiyordu (ölçümle doğrulandı: canlıda "Akbank'ın
    ikinci çeyrek net karı" sorgusu AKBNK'nın yanında GARAN/SISE/YKBNK/
    KCHOL'u de döndürdü). _SIRKET_ALIASES bu tür tickerlar için açık takma
    ad sağlıyor; bu test AKBNK sorgusunun artık yalnızca AKBNK döndürmesini
    doğrular."""
    store = _FakeVectorStore(
        [
            _doc(
                "Akbank ikinci çeyrek net kâr açıkladı, 15,19 milyar TL",
                sirket="AKBNK",
                distance=0.3,
            ),
            _doc(
                "Garanti BBVA ikinci çeyrek net kâr açıkladı",
                sirket="GARAN",
                distance=0.2,
            ),
        ]
    )
    retriever = Retriever(store=store)

    results = retriever.retrieve("Akbank'ın ikinci çeyrek net karı ne kadar")

    sirketler = {r["metadata"]["sirket"] for r in results}
    assert sirketler == {"AKBNK"}


def test_retrieve_takma_adlar_onekte_carpismaz():
    """ "Türk" (THYAO takma adı) ile "Turkcell" (TCELL takma adı) ilk 4
    harfte örtüşüyor ("turk"). İçerik seviyesindeki gevşek önek eşleşmesi
    yüzünden her iki doküman da karşı sorgunun ilk kelime-örtüşme kapısını
    geçebiliyor (bu beklenen/değişmeyen davranış) — ama takma ad eşleşmesi
    önekle değil TAM eşleşmeyle yapılmazsa, bu durumda "başka şirketi ele"
    güvenlik ağı da yanlışlıkla her ikisini "sorguyla eşleşti" sayıp hiçbirini
    elemiyordu (ölçümle doğrulandı: canlıda iki yönde de çapraz bulaşma
    görüldü). Bu test, TAM eşleşme sayesinde güvenlik ağının doğru şirketi
    ayırt edebildiğini doğrular."""
    store = _FakeVectorStore(
        [
            _doc(
                "Turkcell ikinci çeyrek net kâr açıkladı",
                baslik="Turkcell (TCELL) 2026 2. Çeyrek Sonuçları",
                sirket="TCELL",
                distance=0.2,
            ),
            _doc(
                "Türk Hava Yolları ikinci çeyrek net kâr açıkladı",
                baslik="Türk Hava Yolları (THYAO) 2026 2. Çeyrek Sonuçları",
                sirket="THYAO",
                distance=0.3,
            ),
        ]
    )
    retriever = Retriever(store=store)

    tcell_sonuc = retriever.retrieve("Turkcell ikinci çeyrek net karı")
    assert {r["metadata"]["sirket"] for r in tcell_sonuc} == {"TCELL"}

    thyao_sonuc = retriever.retrieve("Türk Hava Yolları ikinci çeyrek")
    assert {r["metadata"]["sirket"] for r in thyao_sonuc} == {"THYAO"}


def test_retrieve_etiketsiz_dokuman_turkiye_kelimesiyle_sizmaz():
    """ "Türkiye" bu korpustaki hemen her makro dokümanda (TÜİK/TCMB vb.)
    geçiyor ve "Turkcell" sorgu kelimesiyle ilk 4 harfte tesadüfen
    örtüşüyor ("turk"). Etiketsiz (sirket boş) genel bir makro dokümanı bu
    yüzden "Turkcell" sorgusuna yanlışlıkla eşleşip, şirket-eleme güvenlik
    ağından muaf olduğu için (etiketsiz dokümanlar kasıtlı olarak muaf
    tutuluyor) sonuçlara sızıyordu (ölçümle doğrulandı: canlıda TÜİK
    işsizlik dokümanı "Turkcell'in ikinci çeyrek sonuçları" sorgusuna
    karıştı). "Türkiye"/"Türk" artık stopword; bu test etiketsiz bir
    dokümanın salt bu kelime üzerinden artık eşleşmediğini doğrular."""
    store = _FakeVectorStore(
        [
            _doc(
                "Turkcell ikinci çeyrek net kâr açıkladı",
                baslik="Turkcell (TCELL) 2026 2. Çeyrek Sonuçları",
                sirket="TCELL",
                distance=0.3,
            ),
            _doc(
                "Türkiye İstatistik Kurumu ikinci çeyrek işsizlik oranını açıkladı",
                baslik="TÜİK İşsizlik Oranını Açıkladı",
                sirket="",
                distance=0.35,
            ),
        ]
    )
    retriever = Retriever(store=store)

    results = retriever.retrieve("Turkcell'in ikinci çeyrek sonuçları neler")

    sirketler = {r["metadata"]["sirket"] for r in results}
    assert sirketler == {"TCELL"}
