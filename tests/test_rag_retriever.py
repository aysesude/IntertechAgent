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


class _TopKAwareFakeVectorStore(VectorStore):
    """Gercek Chroma gibi, mesafeye gore sirali dokumanlari yalnizca ilk
    top_k tanesini dondurur — aday havuzu buyuklugunun (_MIN_CANDIDATE_POOL)
    dogru dokumani havuzun disinda birakip birakmadigini test etmek icin."""

    def __init__(self, documents: list[dict]) -> None:
        self._documents = sorted(documents, key=lambda d: d["distance"])

    def add_documents(self, documents, metadatas) -> None:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError

    def similarity_search(self, query: str, top_k: int = 5, where: dict | None = None):
        return self._documents[:top_k]


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

    results = retriever.retrieve("ASELS net kâr bilanço", sirket="ASELS")

    assert len(results) == 1
    assert results[0]["metadata"]["sirket"] == "ASELS"


def test_retrieve_donem_listesi_ile_son_ceyrekler_filtrelenir():
    store = _FakeVectorStore(
        [
            _doc(
                "ASELS 2026 Ç2 bilançosu net kâr açıklandı",
                sirket="ASELS",
                donem="2026-Q2",
            ),
            _doc(
                "ASELS 2025 Ç1 bilançosu net kâr açıklandı",
                sirket="ASELS",
                donem="2025-Q1",
            ),
        ]
    )
    retriever = Retriever(store=store)

    results = retriever.retrieve(
        "ASELS net kâr bilanço", sirket="ASELS", donem_listesi=["2026-Q1", "2026-Q2"]
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
            _doc(
                "Piyasada ASELSAN dahil savunma sanayi şirketlerinin ikinci çeyrek "
                "net kâr haberleri konuşuluyor",
                sirket="",
                distance=0.4,
            ),
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
            _doc(
                "BIST 100 endeksindeki ASELS bilançosu net kâr açıklandı",
                sirket="ASELS",
                distance=0.3,
            ),
            _doc(
                "BIST 100 endeksindeki THYAO bilançosu net kâr açıklandı",
                sirket="THYAO",
                distance=0.4,
            ),
        ]
    )
    retriever = Retriever(store=store)

    results = retriever.retrieve("BIST 100 endeksindeki şirketlerin net kâr açıklamaları")

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
            _doc(
                "BİM Birleşik Mağazalar hedef fiyat açıklandı",
                sirket="BIMAS",
                distance=0.3,
            ),
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


def test_retrieve_holding_tek_kelimeyle_carpismaz():
    """ "Holding" tek başına aşırı jenerik (Koç Holding, Sabancı Holding,
    ...). KCHOL'un eski takma adı `{"koc", "holding"}` bir OR-kümesiydi;
    bu yüzden "Sabancı Holding" sorgusu salt "holding" kelimesi üzerinden
    KCHOL'u yanlışlıkla eşleştirip SAHOL'u değil onu döndürüyordu
    (ölçümle doğrulandı). _SIRKET_ALIAS_PHRASES artık "koc" VE "holding"in
    BİRLİKTE geçmesini şart koşuyor. Bu test iki yönde de doğru şirketin
    döndüğünü doğrular."""
    store = _FakeVectorStore(
        [
            _doc(
                "Koç Holding ikinci çeyrek net kâr açıkladı",
                baslik="Koç Holding (KCHOL) 2026 2. Çeyrek Sonuçları",
                sirket="KCHOL",
                distance=0.3,
            ),
            _doc(
                "Sabancı Holding ikinci çeyrek net kâr açıkladı",
                baslik="Sabancı Holding (SAHOL) 2026 2. Çeyrek Sonuçları",
                sirket="SAHOL",
                distance=0.3,
            ),
        ]
    )
    retriever = Retriever(store=store)

    koc_sonuc = retriever.retrieve("Koç Holding ikinci çeyrek net kârı")
    assert {r["metadata"]["sirket"] for r in koc_sonuc} == {"KCHOL"}

    sabanci_sonuc = retriever.retrieve("Sabancı Holding ikinci çeyrek net kârı")
    assert {r["metadata"]["sirket"] for r in sabanci_sonuc} == {"SAHOL"}


def test_retrieve_is_bankasi_diger_bankalarla_karismaz():
    """ "İş Bankası" iki ayrı kelimeden ("iş" ve "bankası") oluşuyor; ikisi
    de tek başına anlamsız ("iş" 2 harfe foldlanıp normalde elenirdi,
    "bankası" ise her banka dokümanında geçer). Bu yüzden ISCTR hiçbir
    zaman kendi sirket alanıyla eşleşmiyor, "başka bankayı ele" güvenlik
    ağı devreye girmiyor ve sorgu diğer bankalara karışıyordu (ölçümle
    doğrulandı: canlıda AKBNK/HALKB/YKBNK döndü, ISCTR hiç görünmedi).
    _SHORT_KEYWORD_ALLOWLIST + _SIRKET_ALIAS_PHRASES["ISCTR"] bunu
    düzeltiyor."""
    store = _FakeVectorStore(
        [
            _doc(
                "İş Bankası ikinci çeyrek net kâr açıkladı",
                baslik="Türkiye İş Bankası 2026 2. Çeyrek Sonuçları",
                sirket="ISCTR",
                distance=0.3,
            ),
            _doc(
                "Akbank ikinci çeyrek net kâr açıkladı",
                baslik="Akbank 2026 2. Çeyrek Sonuçları",
                sirket="AKBNK",
                distance=0.3,
            ),
        ]
    )
    retriever = Retriever(store=store)

    results = retriever.retrieve("İş Bankası'nın ikinci çeyrek net kârı ne kadar")

    sirketler = {r["metadata"]["sirket"] for r in results}
    assert sirketler == {"ISCTR"}


def test_retrieve_dar_aday_havuzunda_disarida_kalan_sirket_bulunur():
    """31 `sirket_profili` dokumaninin "Ortaklık yapısı" bolumleri birbirine
    cok benzer bir kaliptla yazildigi icin (hissedar/pay/yuzde gibi ortak
    kelimeler), sorgulanan sirketin kendi dokumani vektor mesafesine gore
    havuzun hemen disinda kalabiliyor (olcumle dogrulandi: "Kardemir'in
    ortaklik yapisi nasil" sorgusunda KRDMD 21. sirada kalip eski havuz
    boyutu 20 iken elenmis, sirket-eleme guvenlik agi hic devreye girmeden
    5 alakasiz sirketin profili donmustu). _MIN_CANDIDATE_POOL'un 30'a
    cikarilmasi, KRDMD'nin kendi dokumaninin havuza girip guvenlik agini
    tetikleyebilmesini sagliyor."""
    diger_sirketler = [
        _doc(
            f"{ticker} ortaklık yapısı hissedar pay yüzde",
            baslik=f"{ticker} Şirket Profili",
            sirket=ticker,
            distance=0.30 + i * 0.01,
        )
        for i, ticker in enumerate(
            [
                "SAHOL",
                "KCHOL",
                "SISE",
                "YKBNK",
                "ARCLK",
                "AKBNK",
                "TUPRS",
                "GARAN",
                "CCOLA",
                "ULKER",
                "TCELL",
                "TOASO",
                "VAKBN",
                "THYAO",
                "HALKB",
                "MGROS",
                "ASELS",
                "ISCTR",
                "PETKM",
                "EKGYO",
            ]
        )
    ]
    kardemir_dokumani = _doc(
        "Kardemir ortaklık yapısı hissedar pay yüzde",
        baslik="Kardemir Şirket Profili",
        sirket="KRDMD",
        distance=0.6911,
    )
    store = _TopKAwareFakeVectorStore([*diger_sirketler, kardemir_dokumani])
    retriever = Retriever(store=store)

    results = retriever.retrieve("Kardemir'in ortaklık yapısı nasıl")

    sirketler = {r["metadata"]["sirket"] for r in results}
    assert sirketler == {"KRDMD"}


def test_retrieve_kesme_isareti_eki_sahte_kelime_uretmez():
    """\\w+ regex'i kesme isaretini kelime siniri saydigi icin ("XYZ
    Teknoloji'nin" -> "xyz" + "teknoloji" + "nin"), 2 harften uzun ekler
    ("nin", "nın", "yle"...) uzunluk barajini gecip jenerik olmayan birer
    "ayirt edici kelime" gibi davranabiliyordu (olcumle dogrulandi: "XYZ
    Teknoloji'nin hisse fiyati ne kadar" sorgusunda "nin" bu sekilde
    THYAO/YKBNK/ISCTR/GARAN'in hedef fiyat raporlarini "bulundu" saydirdi
    — hicbir gercek sirket adi hic eslesmemesine ragmen). Kesme isareti +
    eki tokenlestirmeden once tamamen atmak, uydurma bir sirket sorgusunun
    dogru sekilde "bulunamadi" donmesini sagliyor."""
    store = _FakeVectorStore(
        [
            _doc(
                "THY'nin ikinci çeyrek bilançosu sonrası hedef fiyat açıklandı",
                baslik="THYAO Hedef Fiyat Raporu",
                sirket="THYAO",
                distance=0.4,
            ),
        ]
    )
    retriever = Retriever(store=store)

    results = retriever.retrieve("XYZ Teknoloji'nin hisse fiyatı ne kadar")

    assert results == []


def test_retrieve_uydurma_sirket_holding_enerji_kelimeleriyle_bulunmus_sayilmaz():
    """ "Holding"/"enerji" tek başına aşırı jenerik: onlarca `sirket_profili`
    dokümanında ya şirket adının parçası ("Koç Holding", "Astor Enerji") ya
    da faaliyet alanı olarak geçiyor (ölçümle doğrulandı: "ABC Holding'in
    ikinci çeyrek net kârı nedir" ve "Falanca Enerji'nin ortaklık yapısı
    nasıl" gibi uydurma şirket sorguları, uydurma kısım hiç eşleşmemesine
    rağmen salt "holding"/"enerji"/"ikinci"/"net"/"yapısı" gibi kelimeler
    üzerinden tamamen alakasız gerçek şirketleri "bulundu" saydırdı)."""
    store = _FakeVectorStore(
        [
            _doc(
                "Koç Holding ikinci çeyrek net kârı açıklandı",
                baslik="Koç Holding Şirket Profili",
                sirket="KCHOL",
                distance=0.3,
            ),
            _doc(
                "Astor Enerji ortaklık yapısı hissedar bilgileri",
                baslik="Astor Enerji Şirket Profili",
                sirket="ASTOR",
                distance=0.3,
            ),
        ]
    )
    retriever = Retriever(store=store)

    assert retriever.retrieve("ABC Holding'in ikinci çeyrek net kârı nedir") == []
    assert retriever.retrieve("Falanca Enerji'nin ortaklık yapısı nasıl") == []


def test_retrieve_uydurma_sirket_temettu_odeme_dagitim_kelimeleriyle_bulunmus_sayilmaz():
    """ "Temettü"/"ödeme"/"dağıt-" 31 `sirket_profili` dokümanının TAMAMINDA
    (temettü geçmişi paragrafı eklendikten sonra) geçen jenerik kelimelere
    dönüştü (ölçümle doğrulandı, 2026-08-24: "ABC Holding'in temettü
    ödemesi ne kadar" sorgusu "ödemesi" kelimesinin TCELL'in kendi "ödeme
    tarihi ..." cümlesiyle örtüşmesi yüzünden, "Falanca Enerji'nin temettü
    dağıtımı nasıl" sorgusu ise "dağıtımı" kelimesinin ASTOR'un "dağıtım
    sistemleri"/"dağıtılmasına karar verildi" ifadeleriyle örtüşmesi
    yüzünden, uydurma şirket adı hiç eşleşmemesine rağmen tamamen alakasız
    gerçek şirketleri "bulundu" saydırdı)."""
    store = _FakeVectorStore(
        [
            _doc(
                "Turkcell ortaklık yapısı: ödeme tarihi 9 Aralık 2026 net 3,40 TL temettü",
                baslik="Turkcell Şirket Profili",
                sirket="TCELL",
                distance=0.3,
            ),
            _doc(
                "Astor Enerji elektrik dağıtım sistemleri üretimi, temettü dağıtılmasına karar verildi",
                baslik="Astor Enerji Şirket Profili",
                sirket="ASTOR",
                distance=0.3,
            ),
        ]
    )
    retriever = Retriever(store=store)

    assert retriever.retrieve("ABC Holding'in temettü ödemesi ne kadar") == []
    assert retriever.retrieve("Falanca Enerji'nin temettü dağıtımı nasıl") == []


def test_retrieve_uydurma_sirket_sektor_tarih_yil_kelimeleriyle_bulunmus_sayilmaz():
    """Temettü paragrafının diğer kalıp kelimeleri de aynı gerekçeyle
    jenerikleştirildi (ölçümle doğrulandı, 2026-08-24: 40 uydurma-şirket
    sorgusundan oluşan bir tarama, gerçek şirketlerin 31'inde 30'unun
    sızdığını gösterdi). İki ayrı kaynak: (1) "tarih"/"2026"/"yılında"/
    "başına" temettü cümlesinin ("... tarihi 2026'dır", "hisse başına ...")
    her yerde tekrarlanan iskeleti; (2) daha önce ayrı bir turda eklenen
    BIST sektör sınıflandırması ("sanayi", "metal", "gıda" gibi BİRDEN
    FAZLA şirketin paylaştığı sektör kelimeleri) artık temettü kelimeleriyle
    birlikte oranı dolduruyor. Bu test her iki kaynaktan da örnek içerir."""
    store = _FakeVectorStore(
        [
            _doc(
                "Ereğli Demir Çelik Metal Ana Sanayi sektöründe sınıflandırılmaktadır, "
                "hisse başına temettü ödeme tarihi 2026 yılında",
                baslik="Ereğli Demir Çelik Şirket Profili",
                sirket="EREGL",
                distance=0.3,
            ),
        ]
    )
    retriever = Retriever(store=store)

    assert retriever.retrieve("Örnek Metal Sanayi'nin temettü ödemesi ne kadar") == []
    assert retriever.retrieve("Zafer Madencilik'nin temettü dağıtım tarihi nedir") == []
    assert retriever.retrieve("Vizyon Sanayi 2026 yılında temettü dağıttı mı") == []


def test_retrieve_uydurma_sirket_kurumsal_olay_kelimeleriyle_bulunmus_sayilmaz():
    """Kurumsal olaylar tarihçesi turunda (2026-08-24) 26 profile eklenen
    "halka arz edildi" / "sermaye artırımı" / "satın aldı" kalıp ifadeleri de
    aynı sınıfta jenerikleşti — ölçümle doğrulandı: 32 uydurma-şirket
    sorgusundan oluşan bir tarama 20 sızıntı gösterdi. "Ne zaman"/"hangi"
    soru kalıpları ("zaman", "oldu", "edildi") ile "halka"/"arz"/"sermaye"/
    "artırımı"/"satın"/"aldı"/"geçmişi" kalıp kelimeleri jenerikleştirilerek
    kapatıldı."""
    store = _FakeVectorStore(
        [
            _doc(
                "Petkim hisseleri 9 Temmuz 1990'da Borsa İstanbul'da halka arz "
                "edilmiştir. Şirket STAR Rafineri hissesini satın almıştır, "
                "sermaye artırımı geçmişi bulunmamaktadır.",
                baslik="Petkim Şirket Profili",
                sirket="PETKM",
                distance=0.3,
            ),
        ]
    )
    retriever = Retriever(store=store)

    assert retriever.retrieve("Sahte Sanayi ne zaman halka arz edildi") == []
    assert retriever.retrieve("ABC Holding'in sermaye artırımı ne zaman oldu") == []
    assert retriever.retrieve("Falanca Enerji hangi şirketi satın aldı") == []


def test_halkb_ticker_onegi_halka_kelimesiyle_yanlislikla_eslesmez():
    """ "HALKB" (Halkbank) tickerının foldlanmış hali ("halkb") ile "halka"
    (kamuya — "halka arz"/"halka açık") kelimesi 4 harflik önekte ("halk")
    çakışıyor. Bu, "Aselsan"->"ASELS" gibi ANLAMLI önek örtüşmelerinden
    farklı: "halka" hiçbir bağlamda Halkbank'a işaret etmiyor. Ölçümle
    doğrulandı (2026-08-24): "Sahte Sanayi ne zaman halka arz edildi" ve
    "Ülker ne zaman halka arz edildi" sorguları, sorguda Halkbank'a dair
    hiçbir referans yokken salt bu çakışma yüzünden HALKB'yi "adıyla
    anıldı" sayıp güvenlik ağını (bkz. _sirket_matches_query) yanlışlıkla
    tetikledi ve tamamen alakasız içeriği öne çıkardı."""
    store = _FakeVectorStore(
        [
            _doc(
                "Halkbank hisseleri Borsa İstanbul'da halka arz edilmiştir",
                baslik="Halkbank Şirket Profili",
                sirket="HALKB",
                distance=0.3,
            ),
            _doc(
                "Ülker hisseleri 24 Şubat 2004'te Borsa İstanbul'da halka " "arz edilmiştir",
                baslik="Ülker Bisküvi Şirket Profili",
                sirket="ULKER",
                distance=0.35,
            ),
        ]
    )
    retriever = Retriever(store=store)

    sonuc = retriever.retrieve("Sahte Sanayi ne zaman halka arz edildi")
    assert all(r["metadata"]["sirket"] != "HALKB" for r in sonuc)

    sonuc = retriever.retrieve("Ülker ne zaman halka arz edildi")
    sirketler = {r["metadata"]["sirket"] for r in sonuc}
    assert "HALKB" not in sirketler
    assert "ULKER" in sirketler


# ---------------------------------------------------------------------------
# Sirket adiyla anilan sorgu, kelime-ortusme oranindan muaf
# ---------------------------------------------------------------------------


def test_sirketi_adiyla_anan_sorgu_oran_kapisindan_muaf():
    """Kullanici dokumani olan bir sirketi ADIYLA andiysa sonuc elenmemeli.

    Olculdu (23 Agustos test turu): "ASELS hakkinda ne biliyorsun?" sorgusu
    0.50 oran aliyordu ve kural `> 0.5` oldugu icin dogru dokuman ELENIYOR,
    kullaniciya "veritabaninda bulunamadi" donuyordu. Sirket kodu TAM
    eslesmisti; eleyen sey sorunun geri kalanindaki konusma diliydi
    ("hakkinda", "ne biliyorsun").
    """
    store = _FakeVectorStore(
        [
            _doc(
                "ASELSAN 2026 ikinci ceyrekte net kar acikladi. Gelirler artti.",
                sirket="ASELS",
                baslik="ASELSAN 2026 2. Ceyrek Finansal Sonuclari",
                tur="bilanco",
            )
        ]
    )

    sonuclar = Retriever(store=store).retrieve("ASELS hakkinda ne biliyorsun?")

    assert len(sonuclar) == 1
    assert sonuclar[0]["metadata"]["sirket"] == "ASELS"


def test_korpus_farkli_kelime_kullansa_da_sirket_eslesmesi_yeterli():
    """Kullanicinin sozcugu korpusunkinden farkli olabilir.

    "TUPRS'un BILANCOSUNDA one cikan ne var?" sorgusunda dokumanlar
    "bilanco" demiyor, "finansal sonuclar" diyor. Oran 0.25'e dusuyordu
    (yalnizca `tuprs` ortusuyordu) ve dogru dokuman eleniyordu.
    """
    store = _FakeVectorStore(
        [
            _doc(
                "Tupras 2026 ikinci ceyrek finansal sonuclarini acikladi.",
                sirket="TUPRS",
                baslik="Tupras 2026 2. Ceyrek Finansal Sonuclari",
                tur="bilanco",
            )
        ]
    )

    sonuclar = Retriever(store=store).retrieve("TUPRS'un bilancosunda one cikan ne var?")

    assert len(sonuclar) == 1


def test_muafiyet_BASKA_sirketin_dokumanini_kapsamaz():
    """Muafiyet dar olmali: yalnizca sorguda anilan sirketin dokumani.

    Genis tutulsaydi, iki sirketin neredeyse ayni kalipla yazilmis
    bilancolari arasinda yanlis sirket de kapidan gecerdi — bu kapinin
    engellemek icin var oldugu tam olarak o durum.
    """
    store = _FakeVectorStore(
        [
            _doc(
                "ASELSAN 2026 ikinci ceyrekte net kar acikladi.",
                sirket="ASELS",
                baslik="ASELSAN 2026 2. Ceyrek",
                tur="bilanco",
            ),
            _doc(
                "Turk Hava Yollari 2026 ikinci ceyrekte net kar acikladi.",
                sirket="THYAO",
                baslik="THYAO 2026 2. Ceyrek",
                tur="bilanco",
            ),
        ]
    )

    sonuclar = Retriever(store=store).retrieve("ASELS hakkinda ne biliyorsun?")

    donen_sirketler = {r["metadata"]["sirket"] for r in sonuclar}
    assert donen_sirketler == {"ASELS"}, "THYAO dokumani sizmamali"


def test_muafiyet_alakasiz_sorguyu_kapidan_gecirmez():
    """Hicbir sirketle eslesmeyen sorgu icin kapi AYNEN duruyor.

    Muafiyet oran kuralini gevsetmiyor, yalnizca deterministik olarak
    alakali oldugu kanitlanmis sonucu kapsam disi birakiyor.
    """
    store = _FakeVectorStore(
        [
            _doc(
                "ASELSAN 2026 ikinci ceyrekte net kar acikladi.",
                sirket="ASELS",
                baslik="ASELSAN 2026 2. Ceyrek",
                tur="bilanco",
            )
        ]
    )

    assert Retriever(store=store).retrieve("Bitcoin fiyati ne kadar") == []


# ---------------------------------------------------------------------------
# "Kaynaklar" listesine alakasiz dokuman sizmasi — analist canli test turu
# (2026-08-26): "bilgi yok" cevabinin altina bile alakasiz sirket
# dokumanlari "Kaynaklar" olarak yaziliyordu.
# ---------------------------------------------------------------------------


def test_altin_sorgusu_alti_ayli_kelimesiyle_yanlislikla_eslesmez():
    """ "altin" (gold) ile "alti" (six, "alti aylik"/"ilk alti ay" hemen her
    bilancoda geciyor) 4 harflik onekte cakisiyordu (olculdu): "Altin
    piyasasinda ne oluyor" sorgusu RAG'da altin fiyatina dair hic icerik
    olmamasina ragmen TOASO gibi tamamen alakasiz sirketleri "bulundu"
    saydirip "Kaynaklar" listesine sokuyordu."""
    store = _FakeVectorStore(
        [
            _doc(
                "Tofas 2026 ikinci ceyrekte, ilk alti aylik donemde net kar acikladi.",
                sirket="TOASO",
                baslik="Tofas 2026 2. Ceyrek",
                tur="bilanco",
                distance=0.594,
            )
        ]
    )

    assert Retriever(store=store).retrieve("Altin piyasasinda ne oluyor") == []


def test_altin_sorgusu_altinda_kelimesiyle_de_yanlislikla_eslesmez():
    """ "altinda" (below/under, "beklentilerin altinda" gibi ifadeler) da
    ayni 4 harflik onekte ("alti") cakisiyor — "alti" (six) ile ayni aile,
    tek tek istisna yerine "altin" icin tam eslesme zorunlu kilindi."""
    store = _FakeVectorStore(
        [
            _doc(
                "Net kar, piyasa beklentisinin altinda gerceklesti.",
                sirket="SISE",
                baslik="Sisecam 2026 2. Ceyrek",
                tur="bilanco",
                distance=0.607,
            )
        ]
    )

    assert Retriever(store=store).retrieve("Altin piyasasinda ne oluyor") == []


def test_kap_ve_gelisme_kelimeleri_jenerik_sayilir():
    """ "KAP" (Kamuyu Aydinlatma Platformu) hemen her dokumanin kaynaginda
    geciyor, "gelisme" de genel bir haber/olay kelimesi. Olculdu: "KAP'a
    gore deniz bank hakkinda guncel bir gelisme var mi?" sorgusu —
    DenizBank RAG'da hic yok — "kap"+"gelisme" uzerinden Is Bankasi gibi
    tamamen alakasiz bankalari "bulundu" saydirip "Kaynaklar" listesine
    sokuyordu."""
    store = _FakeVectorStore(
        [
            _doc(
                "Is Bankasi KAP'a yeni bir gelisme bildirdi, ikinci ceyrek net kar acikladi.",
                sirket="ISCTR",
                baslik="Is Bankasi 2026 2. Ceyrek",
                tur="bilanco",
                distance=0.553,
            )
        ]
    )

    assert (
        Retriever(store=store).retrieve("KAP'a gore deniz bank hakkinda guncel bir gelisme var mi")
        == []
    )


def test_nakit_akis_tablosu_kelimeleri_jenerik_sayilir():
    """ "Nakit akış tablosu" başlığı 2026-08-26'da 23 bilanço dokümanına
    eklendi — "temettü"/"halka arz" ile aynı sınıfta jenerikleşti. Ölçümle
    doğrulandı: "BİM'in nakit akış tablosu nasıl?" (BIMAS için bu içerik
    hiç eklenmedi) sorgusu "nakit"/"akış"/"tablosu" üzerinden tamamen
    alakasız şirketleri "bulundu" saydırıp "Kaynaklar" listesine sokuyordu."""
    store = _FakeVectorStore(
        [
            _doc(
                "## Nakit akış tablosu\n\nVakıfBank'ın işletme faaliyetlerinden "
                "nakit akışı negatif gerçekleşti.",
                sirket="VAKBN",
                baslik="VakıfBank 2026 2. Çeyrek",
                tur="bilanco",
                distance=0.397,
            )
        ]
    )

    assert Retriever(store=store).retrieve("BİM'in nakit akış tablosu nasıl?") == []


def test_referans_dokumani_kelime_ortusme_kapisindan_muaf():
    """ "tur: referans" dokümanları (TFRS/finansal oran/kurumsal olay
    terimleri sözlüğü) jenerik kelime kapısından muaf: bir kavramı
    TANIMLAYAN doküman, tanımladığı kelimeleri sıkça kullanır ama bu
    kelimeler bilanço dokümanlarının boilerplate açılışında da geçtiği
    için jenerik sayılmak zorunda kalıyor (bkz. "nakit"/"tablosu"/"kap").
    İkisi çakışınca kavramı tanımlayan TEK doğru kaynak da elenip sorgu
    tamamen boş dönüyordu (ölçümle doğrulandı, 2026-08-26): "Konsolide
    finansal tablo ne demek?" sorgusu. Şirket dokümanlarının aksine burada
    "yanlış şirket" riski yok, muafiyet güvenli."""
    store = _FakeVectorStore(
        [
            _doc(
                "TFRS 10, bir ana ortaklığın kontrol ettiği bağlı ortaklıklarla "
                "birlikte konsolide finansal tablo sunmasını düzenler.",
                baslik="TFRS Temel Standartlar Sözlüğü",
                tur="referans",
                distance=0.335,
            )
        ]
    )

    sonuclar = Retriever(store=store).retrieve("Konsolide finansal tablo ne demek?")

    assert len(sonuclar) == 1
    assert sonuclar[0]["metadata"]["tur"] == "referans"
