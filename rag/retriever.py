"""Piyasa Araştırma Ajanı'nın kullanacağı retrieval arayüzü.

Saf DB tabanlı RAG: LLM yanıt üretmez, internetten canlı veri çekmez.
`data/documents/` altına eklenen dokümanlar `rag.ingest` ile veritabanına
işlenir; burada yalnızca o veritabanı sorgulanır. Sorguya yeterince yakın bir
sonuç yoksa "bulunamadı" anlamına gelen boş liste döner — uydurma yok (AK 5.5).

Hibrit eşleştirme: yalnızca vektör mesafesi küçük veri setlerinde ve kısa
sorularda yanıltıcı olabiliyor (alakasız bir sorgu, gerçekten alakalı bir
sorgudan daha düşük mesafe alabiliyor — ölçümle doğrulandı). Bu yüzden bir
sonuç yalnızca hem mesafe eşiğini geçerse HEM DE sorguyla en az bir gerçek
kelime paylaşırsa "bulundu" sayılır."""

import re

from app.core.config import settings
from rag.vector_store import VectorStore, get_vector_store

NOT_FOUND_MESSAGE = "Veritabanımızda bu sorguyla ilgili doğrulanmış bir bilgi bulunamadı."

# Kelime örtüşmesi kontrolünde göz ardı edilecek, ayırt edici olmayan Türkçe
# kelimeler (aksansız/ASCII-katlanmış halleriyle — bkz. _normalize). Bunlar
# olmasaydı "ne kadar", "hakkında" gibi hemen her sorguda geçen kelimeler,
# alakasız dokümanlarla bile sahte örtüşme yaratırdı.
_STOPWORDS = {
    "ve",
    "veya",
    "ile",
    "bir",
    "bu",
    "su",
    "o",
    "de",
    "da",
    "mi",
    "mu",
    "midir",
    "ne",
    "kadar",
    "icin",
    "gibi",
    "cok",
    "az",
    "en",
    "daha",
    "olan",
    "olarak",
    "gore",
    "kac",
    "hangi",
    "nasil",
    "nedir",
    "hakkinda",
    "bilgi",
    "lutfen",
    "acaba",
    "son",
    "var",
    "yok",
    # "Türkiye"/"Türk" bu korpusta (TCMB/TÜİK/Hazine vb. makro dokümanlar
    # yüzünden) neredeyse HER dokümanda geçiyor — ayırt edici gücü "ve"/
    # "ile" kadar düşük. Ayrıca "Turkcell" sorgu kelimesiyle ilk 4 harfte
    # tesadüfen örtüşüyor ("turk"): sorgu "Turkcell'in ikinci çeyrek
    # sonuçları" iken, sirket alanı boş (ve bu yüzden şirket-eleme güvenlik
    # ağından muaf) herhangi bir TÜİK/TCMB dokümanı sadece "Türkiye"
    # kelimesi üzerinden yanlışlıkla eşleşip sonuçlara karışabiliyordu
    # (ölçümle doğrulandı: TÜİK işsizlik dokümanı "Turkcell" sorgusuna
    # sızdı). Stopword yapmak hem bu çakışmayı hem de düşük bilgi değerini
    # aynı anda çözüyor.
    "turkiye",
    "turk",
}

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_MIN_KEYWORD_LEN = 3
_PREFIX_MATCH_LEN = (
    4  # Türkçe çekim ekleri için (şirket/şirketin gibi) tam eşleşme yerine önek karşılaştırması
)

# Chroma'dan çekilecek en az aday sayısı (top_k'dan bağımsız): ham vektör
# mesafesi doğru dokümanı her zaman ilk birkaç sıraya koymuyor (ölçümle
# doğrulandı), bu yüzden süzme daha geniş bir havuz üzerinde yapılır. 31
# `sirket_profili` dokümanının "Ortaklık yapısı" bölümleri birbirine çok
# benzer bir kalıpla yazıldığı için (hissedar/pay/yüzde gibi ortak kelimeler),
# bazı şirketlerin kendi dokümanı havuzun hemen dışında kalabiliyor (ölçümle
# doğrulandı: "Kardemir'in ortaklık yapısı nasıl" sorgusunda KRDMD 21.
# sırada kalıp havuz 20 iken elenmiş, bunun yerine şirket-eleme güvenlik ağı
# hiç devreye girmeden 5 alakasız şirketin profili dönmüştü). Havuz
# genişletilerek KRDMD'nin kendi dokümanı havuza girip güvenlik ağını
# (bkz. _sirket_matches_query) tetikleyebiliyor.
_MIN_CANDIDATE_POOL = 30

# Türkçe klavyesi olmayan / aksan girmeyen kullanıcılar için: "FAVOK" ile
# "FAVÖK", "sirket" ile "şirket" aynı kelime sayılsın diye ASCII'ye katlanır.
_TURKISH_FOLD_MAP = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u"})


def _normalize(text: str) -> str:
    # Python'un str.lower()'ı Türkçe büyük "İ" (U+0130) harfini Unicode
    # varsayılanına göre "i" + birleşen nokta işaretine (U+0307) çevirir, tek
    # bir "i" harfine değil. Bu, \w+ regex'inin o karakteri kelime sınırı
    # sayıp "BİM" gibi bir kelimeyi "bi" + "m" gibi anlamsız parçalara
    # bölmesine yol açıyordu (ölçümle doğrulandı: "BİM hedef fiyat" sorgusu
    # şirket adını hiç kelime olarak taşımıyordu). Düz "İ" büyük harfi
    # lower()'dan ÖNCE normal "i"ye çevrilerek bu parçalanma engellenir.
    return text.replace("İ", "i").lower().translate(_TURKISH_FOLD_MAP)


# "İş" ("İş Bankası") foldlanınca "is" olur — 2 harf, _MIN_KEYWORD_LEN'in
# altında kaldığı için normalde tamamen elenirdi. Tek başına anlamsız
# ("is" fiili/eki gibi başka bağlamlarda da geçebilir) olduğu için genel
# uzunluk sınırını düşürmek yerine yalnızca bu kelimeye özel bir istisna
# tanımlanır — _SIRKET_ALIAS_PHRASES["ISCTR"] zaten "bankasi" ile BİRLİKTE
# geçmesini şart koşuyor, tek başına bir şeyi tetiklemiyor.
_SHORT_KEYWORD_ALLOWLIST = {"is"}

# Türkçe kesme işaretinden sonraki ek ("Kardemir'in", "XYZ Teknoloji'nin"),
# \w+ regex'i kesme işaretini kelime sınırı saydığı için kendi başına ayrı
# bir "kelime" haline geliyor. Kısa ekler (2 harf: "in", "de") zaten
# _MIN_KEYWORD_LEN altında kalıp elenir, ama 3+ harfli ekler ("nin", "nın",
# "yle", "ndan") uzunluk barajını geçip anlamsız birer "ayırt edici kelime"
# gibi davranıyordu (ölçümle doğrulandı: "XYZ Teknoloji'nin hisse fiyatı ne
# kadar" sorgusunda "nin" jenerik olmayan bir eşleşme sayılıp THYAO/YKBNK/
# ISCTR/GARAN'ın hedef fiyat raporlarını "bulundu" saydırdı — hiçbir gerçek
# şirket adı hiç eşleşmemesine rağmen). Kesme işareti + sonrasındaki ek,
# kelimeleştirmeden ÖNCE tamamen atılır; böylece "kardemir'in" yalnızca
# "kardemir" kelimesini üretir, hiçbir ek kelime türetmez.
_APOSTROPHE_SUFFIX_RE = re.compile(r"'\w+")


def _keywords(text: str) -> set[str]:
    normalized = _APOSTROPHE_SUFFIX_RE.sub("", _normalize(text))
    tokens = _WORD_RE.findall(normalized)
    return {
        t
        for t in tokens
        if (len(t) >= _MIN_KEYWORD_LEN or t in _SHORT_KEYWORD_ALLOWLIST) and t not in _STOPWORDS
    }


# Bir sonucun "yeterince örtüşüyor" sayılması için sorgu kelimelerinin en az
# yarısından FAZLASININ eşleşmesi gerekir (tam yarısı yetmez — bkz. altta).
_MIN_KEYWORD_OVERLAP_RATIO = 0.5

# "hisse", "fiyat", "şirket" gibi kelimeler neredeyse HER bilanço/analiz
# dokümanında birlikte geçiyor (bkz. _shares_a_keyword). Korpus büyüdükçe,
# uydurma bir şirket adı içeren ama tesadüfen bu jenerik kelimelerin
# üçünü/dördünü barındıran bir sorgu ("xyzabc uydurma bir şirketin hisse
# fiyatı ne kadar" gibi), gerçek bir şirket adı hiç eşleşmese bile salt bu
# jenerik kelimelerle >0.5 oranını geçebiliyor (ölçümle doğrulandı: THYAO
# analist raporunun "Bilanço bağlamı" parçasıyla 3/5 oranında eşleşip
# "bulunamadı" yerine alakasız bir gerçek doküman döndü). Bu yüzden eşleşen
# kelimelerin EN AZ BİRİ bu jenerik listenin dışında olmalı — yalnızca
# jenerik finans klişeleriyle örtüşen bir sonuç artık kabul edilmiyor.
_GENERIC_FINANCE_TERMS = {
    "hisse",
    "fiyat",
    "sirket",
    "ceyrek",
    "bilanco",
    "milyar",
    "hedef",
    "yuzde",
    "kurum",
    "rapor",
    "yatirim",
    "aciklama",
    "donem",
    "artis",
    "ortalama",
    "tavsiye",
}


def _query_keyword_matches(qk: str, candidate_keywords: set[str]) -> bool:
    prefix_len = min(len(qk), _PREFIX_MATCH_LEN)
    qk_prefix = qk[:prefix_len]
    return any(len(ck) >= prefix_len and ck[:prefix_len] == qk_prefix for ck in candidate_keywords)


def _is_generic_finance_keyword(word: str) -> bool:
    prefix_len = min(len(word), _PREFIX_MATCH_LEN)
    word_prefix = word[:prefix_len]
    return any(
        len(term) >= prefix_len and term[:prefix_len] == word_prefix
        for term in _GENERIC_FINANCE_TERMS
    )


def _shares_a_keyword(query_keywords: set[str], candidate_keywords: set[str]) -> bool:
    """Gerçek verideki iki bulgu: "hisse", "çeyrek", "net kâr" gibi finans
    jargonu neredeyse her dokümanda geçiyor. Tek bir ortak kelime yeterli
    sayılırsa (eski davranış) alakasız bir sorgu ("Bitcoin fiyatı ne kadar")
    salt "fiyat" kelimesi üzerinden bir analist raporuyla eşleşiyor; ya da iki
    şirketin de "ikinci çeyrek net kâr açıkladı" gibi neredeyse aynı kalıpla
    yazılmış bilançoları arasında, sorgudaki asıl şirket adı hiç eşleşmese
    bile jenerik kelimeler üzerinden yanlış şirket kapıdan geçebiliyor
    (ölçümle doğrulandı — gerçek THYAO/ASELSAN dokümanlarıyla test edildi).

    Bu yüzden "en az yarısından fazlası eşleşsin" kuralı var: `> 0.5`, `>= 0.5`
    değil — 2 kelimelik bir sorguda tek kelimenin (%50) eşleşmesi yetmemeli,
    ikisinin de eşleşmesi gerekir; bu da "Bitcoin fiyatı" gibi sorguları
    tek kelimeden (fiyat) geçirmeyi engeller.

    Ama oran tek başına yetmiyor: sorgu 3+ kelimeliyse ve bu kelimelerin
    çoğu "hisse", "fiyat", "şirket" gibi jenerik finans klişesiyse, tümü
    tesadüfen tek bir dokümanda birlikte geçtiği için oran barajını
    geçebiliyor — sorgudaki asıl (uydurma ya da alakasız) konu hiç
    eşleşmemiş olsa bile (ölçümle doğrulandı, bkz. _GENERIC_FINANCE_TERMS).
    Bu yüzden eşleşen kelimelerden EN AZ BİRİNİN bu jenerik listenin
    dışında olması da şart — yalnızca klişelerle örtüşen bir sonuç artık
    "bulundu" sayılmıyor."""
    if not query_keywords:
        return False
    matched = {qk for qk in query_keywords if _query_keyword_matches(qk, candidate_keywords)}
    if not matched:
        return False
    ratio_yeterli = len(matched) / len(query_keywords) > _MIN_KEYWORD_OVERLAP_RATIO
    belirgin_eslesme_var = any(not _is_generic_finance_keyword(qk) for qk in matched)
    return ratio_yeterli and belirgin_eslesme_var


def _result_keywords(result: dict) -> set[str]:
    text = result.get("content", "")
    metadata = result.get("metadata") or {}
    for key in ("baslik", "sirket", "tur", "kaynak"):
        value = metadata.get(key)
        if value:
            text = f"{text} {value}"
    return _keywords(text)


# Ticker kodu (frontmatter'daki `sirket` alanı) ile şirketin günlük dilde
# kullanılan adı her zaman aynı 4 harfle başlamıyor — ör. "AKBNK" foldlanınca
# "akbnk" olur, "Akbank" ise "akbank"; 4 harflik önekleri "akbn" ile "akba"
# farklı, dolayısıyla önek eşleşmesi hiç tetiklenmiyor. Bu durumda
# _sirket_matches_query hiçbir sonuç için True dönmüyor, "başka şirketi
# tamamen ele" güvenlik ağı devreye girmiyor ve sorguyla alakasız şirketler
# sızabiliyor (ölçümle doğrulandı: "Akbank'ın ikinci çeyrek net karı"
# sorgusu AKBNK'nın yanında GARAN/SISE/YKBNK/KCHOL'u de döndürdü — hiçbiri
# tesadüfen önek paylaşmıyordu). Diğer tickerlar (ASELS/Aselsan,
# GARAN/Garanti, TUPRS/Tüpraş, EREGL/Ereğli, SISE/Şişecam, BIMAS/BİM)
# tesadüfen ilk harflerde örtüştüğü için soruna girmiyor; örtüşmeyenler için
# açık takma ad listesi.
_SIRKET_ALIASES: dict[str, set[str]] = {
    "AKBNK": {"akbank"},
    # "turk" burada yok: artık stopword (bkz. _STOPWORDS), sorgu
    # kelimeleri arasında hiç görünmez — eklense de hiçbir zaman
    # eşleşmeyecek ölü bir giriş olurdu.
    "THYAO": {"hava", "yollari", "thy"},
    "PGSUS": {"pegasus"},
    "TCELL": {"turkcell"},
    # "otomotiv" burada YOK: bu kelime tek başına aşırı jenerik ("Doğuş
    # Otomotiv" sorgusu FROTO'yu yanlışlıkla eşleştiriyordu — ölçümle
    # doğrulandı). "ford"/"otosan" zaten yeterince ayırt edici.
    "FROTO": {"ford", "otosan"},
    "MGROS": {"migros"},
    "SAHOL": {"sabanci"},
    "ARCLK": {"arcelik"},
    "TOASO": {"tofas"},
    "VAKBN": {"vakifbank", "vakiflar"},
    "TTKOM": {"telekom"},
    "CCOLA": {"coca", "cola", "icecek"},
    "DOAS": {"dogus"},
    "EKGYO": {"emlak", "konut"},
    "KRDMD": {"kardemir"},
}

# Bazı şirket adları TEK kelimeyle aşırı jenerik oluyor: "holding" onlarca
# dokümanda geçiyor (Koç Holding, Sabancı Holding, ...), "kredi" ve
# "bankası" da öyle (her banka dokümanında var). Bu yüzden KCHOL'un eski
# `{"koc", "holding"}` OR-eşleşmesi, "Sabancı Holding" sorgusunda salt
# "holding" kelimesi üzerinden KCHOL'u yanlışlıkla eşleştiriyordu (ölçümle
# doğrulandı). Bu tickerlar için OR yerine, listedeki kelimelerin TÜMÜNÜN
# sorguda birlikte geçmesini şart koşan bir "ifade" (phrase) tanımlanır —
# tek başına "holding"/"kredi"/"bankası" artık hiçbir şeyi tetiklemiyor.
_SIRKET_ALIAS_PHRASES: dict[str, list[set[str]]] = {
    "KCHOL": [{"koc", "holding"}],
    "YKBNK": [{"yapi", "kredi"}],
    # "iş" ("İş Bankası") normalde _MIN_KEYWORD_LEN altında kalıp elenir;
    # bkz. _SHORT_KEYWORD_ALLOWLIST. "bankası" tek başına aşırı jenerik
    # olduğu için yalnızca "iş" + "bankası" birlikte geçtiğinde eşleşir.
    "ISCTR": [{"is", "bankasi"}],
}


def _sirket_matches_query(result: dict, query_keywords: set[str]) -> bool:
    """İki farklı şirketin bilançosu neredeyse aynı jenerik kalıpla
    yazıldığında ("ikinci çeyrek net kâr açıklandı") ikisi de aynı kelime-
    örtüşme oranını alabiliyor (ölçümle doğrulandı: gerçek THYAO/ASELSAN
    dokümanlarıyla). Bu durumda, sonucun KENDİ `sirket` alanı sorgudaki
    kelimelerden biriyle eşleşiyorsa sıralamada öne alınır — jenerik içerik
    kelimeleri değil, dokümanın ait olduğu şirketin kendisi tercih sebebidir.

    Ticker kodu (`sirket_keywords`) hâlâ 4 harflik ÖNEK ile karşılaştırılır
    (ör. "Aselsan" -> "asel" -> "ASELS" ile örtüşüyor, mevcut davranış
    korunuyor). Ama _SIRKET_ALIASES TAM eşleşmeyle karşılaştırılır, önekle
    değil: "Türk" (THYAO takma adı) ile "Turkcell" (TCELL takma adı) ilk 4
    harfte örtüşüyor ("turk"), önek karşılaştırması kullanılsaydı "Turkcell
    ikinci çeyrek sonuçları" sorgusu THYAO'yu da, "Türk Hava Yolları ikinci
    çeyrek" sorgusu TCELL'i de yanlışlıkla eşleştirirdi (ölçümle
    doğrulandı). Takma adlar zaten tam, belirli kelimeler olarak seçildiği
    için tam eşleşme yeterli ve bu çapraz bulaşmayı engelliyor.

    _SIRKET_ALIAS_PHRASES ayrıca kontrol edilir: bir tickerın listedeki
    HER kelime grubundan biri sorguda TAMAMEN geçiyorsa eşleşme sayılır —
    "holding"/"kredi"/"bankası" gibi tek başına aşırı jenerik kelimelerin
    yalnızca belirli bir şirket adıyla BİRLİKTE geçtiğinde anlam
    kazanmasını sağlar (bkz. _SIRKET_ALIAS_PHRASES tanımındaki not)."""
    sirket = (result.get("metadata") or {}).get("sirket")
    if not sirket:
        return False
    ticker = str(sirket).upper()
    sirket_keywords = _keywords(str(sirket))
    if any(_query_keyword_matches(qk, sirket_keywords) for qk in query_keywords):
        return True
    aliases = _SIRKET_ALIASES.get(ticker)
    if aliases and query_keywords & aliases:
        return True
    phrases = _SIRKET_ALIAS_PHRASES.get(ticker)
    return bool(phrases and any(phrase <= query_keywords for phrase in phrases))


def _document_date(result: dict) -> str:
    """Dokümanın `tarih` metadata'sı, sıralamaya uygun metin olarak.

    `tarih` ingest sırasında ISO (YYYY-AA-GG) biçiminde yazılıyor; bu biçimde
    metin sıralaması kronolojik sıralamaya eşittir, ayrıştırmaya gerek yok.
    Alan boşsa boş metin döner ve o parça en eskiye düşer — tarihsiz bir
    doküman "en güncel" sayılmamalı."""
    return str((result.get("metadata") or {}).get("tarih") or "")


def _build_where(
    sirket: str | None, donem: str | None, donem_listesi: list[str] | None, tur: str | None
) -> dict | None:
    """Chroma metadata filtresi üretir. Şirket/dönem/tür verilirse arama uzayı
    vektör benzerliği hesaplanmadan ÖNCE daraltılır — bu, benzerlik aramasının
    yapısal olarak yanlış şirket/dönem döndürmesini engeller (post-filter tek
    başına yeterli değil: ilk top_k sonucun tamamı yanlış şirketten gelebilir
    ve gerçek eşleşme hiç görünmeyebilir)."""
    if donem and donem_listesi:
        raise ValueError("donem ve donem_listesi birlikte verilemez")

    kosullar = []
    if sirket:
        kosullar.append({"sirket": sirket})
    if donem:
        kosullar.append({"donem": donem})
    if donem_listesi:
        kosullar.append({"donem": {"$in": donem_listesi}})
    if tur:
        kosullar.append({"tur": tur})

    if not kosullar:
        return None
    if len(kosullar) == 1:
        return kosullar[0]
    return {"$and": kosullar}


def _matches_filters(
    result: dict,
    sirket: str | None,
    donem: str | None,
    donem_listesi: list[str] | None,
    tur: str | None,
) -> bool:
    """Son filtre: Chroma'nın `where`'i doğru uyguladığını varsaymak yerine
    dönen sonucu istenen alanlara karşı tekrar doğrular (bkz. Market Research
    Ajanı tasarımındaki "son filtre" adımı — vektör aramasının yapısal olarak
    engelleyemediği yanılsamalara karşı ikinci bir savunma hattı)."""
    metadata = result.get("metadata") or {}
    if sirket and metadata.get("sirket") != sirket:
        return False
    if donem and metadata.get("donem") != donem:
        return False
    if donem_listesi and metadata.get("donem") not in donem_listesi:
        return False
    if tur and metadata.get("tur") != tur:
        return False
    return True


class Retriever:
    def __init__(self, store: VectorStore | None = None) -> None:
        self._store = store or get_vector_store()

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        *,
        sirket: str | None = None,
        donem: str | None = None,
        donem_listesi: list[str] | None = None,
        tur: str | None = None,
    ) -> list[dict[str, str]]:
        """Sorguya en yakın doküman parçalarını döndürür.

        `sirket`/`donem`/`donem_listesi`/`tur` verilirse deterministik
        filtre olarak uygulanır (hem arama uzayını daraltan ön filtre, hem
        dönen sonucu doğrulayan son filtre) — serbest metin benzerliğinin
        yanlış şirket/dönem döndürmesi yapısal olarak engellenir. Bu alanlar
        `None` bırakılırsa (bugünkü tek çağıran, search_market_news, hep
        böyle çağırır) davranış öncekiyle aynıdır: yalnızca serbest metin
        araması + mesafe/kelime örtüşmesi kontrolü.

        Bir sonuç ancak hem Chroma mesafesi `settings.rag_distance_threshold`
        altındaysa HEM DE sorguyla en az bir anlamlı kelime paylaşıyorsa (ya
        da yapılandırılmış filtrelerle geldiyse) döner. Hiçbiri sağlanmazsa
        boş liste döner."""
        query = query.strip()
        if not query:
            return []

        query_keywords = _keywords(query)
        if not query_keywords:
            return []

        # Chroma'dan istenen top_k'dan daha GENİŞ bir aday havuzu çekilir: ham
        # vektör mesafesi doğru dokümanı ilk top_k'ya sokmayabiliyor (ör. iki
        # şirketin bilançosu neredeyse aynı kalıpla yazıldığında yanlış şirket
        # mesafece daha yakın çıkabiliyor — ölçümle doğrulandı). Süzme
        # (mesafe eşiği + kelime örtüşmesi) bu geniş havuz üzerinde yapılır,
        # sonra çağıranın istediği top_k'ya kesilir.
        candidate_pool = max(top_k * 4, _MIN_CANDIDATE_POOL)
        where = _build_where(sirket, donem, donem_listesi, tur)
        results = self._store.similarity_search(query, top_k=candidate_pool, where=where)

        filtered = [
            r
            for r in results
            if r.get("distance", 1.0) <= settings.rag_distance_threshold
            and _shares_a_keyword(query_keywords, _result_keywords(r))
            and _matches_filters(r, sirket, donem, donem_listesi, tur)
        ]

        # Sorgu belirli bir şirkete işaret ediyorsa (sonuçlardan biri kendi
        # `sirket` alanıyla eşleştiyse), BAŞKA bir şirkete etiketli sonuçlar
        # tamamen elenir — yalnızca sıralamada geriye atmak yetmiyordu:
        # "ASELSAN'ın ... nasıl?" sorusuna THYAO'nun parçaları da (aynı
        # jenerik bilanço kalıbı yüzünden) kelime-örtüşme eşiğini geçip
        # sonuca karışabiliyordu (ölçümle doğrulandı). Etiketsiz genel
        # haber/makro dokümanlar (`sirket` boş) bu elemeden muaf — "ASELSAN
        # hakkında haber var mı" sorusunda ASELSAN'ı yalnızca geçerken anan
        # genel bir piyasa haberi hâlâ geçerli bir sonuçtur.
        if any(_sirket_matches_query(r, query_keywords) for r in filtered):
            filtered = [
                r
                for r in filtered
                if not (r.get("metadata") or {}).get("sirket")
                or _sirket_matches_query(r, query_keywords)
            ]

        # Chroma zaten mesafeye göre sıralı döndürdüğü için stabil sort,
        # kendi şirketi sorguyla eşleşen sonuçları öne alırken aynı grup
        # içinde mesafe sırasını korur.
        filtered.sort(key=lambda r: not _sirket_matches_query(r, query_keywords))
        return filtered[:top_k]

    def retrieve_for_symbols(
        self,
        symbols: list[str],
        *,
        top_k_per_symbol: int = 2,
        types: list[str] | None = None,
        query: str | None = None,
    ) -> dict[str, list[dict]]:
        """Verilen semboller için, sembol başına GRUPLANMIŞ ve TARİHE GÖRE
        yeniden eskiye sıralı doküman parçaları döndürür.

        `retrieve()`'den üç yapısal farkı var ve üçü de kasıtlıdır:

        1. KELİME ÖRTÜŞMESİ ARANMAZ. `retrieve()`, serbest metin sorgusunun
           alakasız doküman çekmesini kelime örtüşmesiyle engelliyor. Burada
           öyle bir sorgu yok: arama uzayı `sirket` metadata'sıyla zaten
           belirli varlıklara kilitli, dolayısıyla dönen her parça tanımı
           gereği o varlığa ait. Kelime kapısını burada uygulamak
           "portföyümle ilgili haberler" gibi jenerik bir istekte HER
           sonucu elerdi (sorgu metni doküman metniyle kelime paylaşmaz).

        2. MESAFE EŞİĞİ UYGULANMAZ. Aynı gerekçe: alaka kararını vektör
           mesafesi değil, deterministik `sirket` filtresi veriyor. Eşik
           burada yalnızca doğru şirkete ait gerçek dokümanları eleyebilirdi.

        3. SIRALAMA TARİHE GÖRE. İş analisti "GÜNCEL haber, market bilgileri
           ve analist yorumları" istiyor; benzerlik sırası güncelliği
           garanti etmez (2026-04 tarihli bir analiz, 2026-08 tarihlinin
           önüne geçebiliyor). `tarih` ISO (YYYY-AA-GG) yazıldığı için metin
           sıralaması kronolojik sıralamaya eşittir.

        Tek bir vektör sorgusu yapılır (sembol başına ayrı sorgu değil):
        embedding hesabı çağrı başına ~50-100 ms ve 15 varlıklı bir portföy
        bunu 15 kez ödeyemez. Gruplama Python tarafında yapılır.

        Dokümanı olmayan sembol sonuç sözlüğünde HİÇ yer almaz — çağıran
        taraf eksikliği görüp kullanıcıya bildirebilsin diye (AK 5.5).
        """
        symbols = [s for s in dict.fromkeys(symbols) if s]
        if not symbols or top_k_per_symbol < 1:
            return {}

        kosullar: list[dict] = [{"sirket": {"$in": symbols}}]
        if types:
            kosullar.append({"tur": {"$in": list(types)}})
        where = kosullar[0] if len(kosullar) == 1 else {"$and": kosullar}

        # Havuz cömert tutuluyor: Chroma `where` süzgecinden geçen sonuçlar
        # arasından en yakın n taneyi döndürür. Havuz darsa bir sembolün tüm
        # parçaları başka sembollerinkinin gerisinde kalıp hiç görünmeyebilir.
        candidate_pool = max(len(symbols) * top_k_per_symbol * 4, _MIN_CANDIDATE_POOL)
        results = self._store.similarity_search(
            query or " ".join(symbols), top_k=candidate_pool, where=where
        )

        gruplar: dict[str, list[dict]] = {}
        for result in results:
            metadata = result.get("metadata") or {}
            sirket = str(metadata.get("sirket") or "")
            # Son filtre: Chroma'nın `where`'i doğru uyguladığı varsayılmaz
            # (bkz. _matches_filters'daki aynı gerekçe).
            if sirket not in symbols:
                continue
            if types and metadata.get("tur") not in types:
                continue
            gruplar.setdefault(sirket, []).append(result)

        for sirket, parcalar in gruplar.items():
            parcalar.sort(key=_document_date, reverse=True)
            gruplar[sirket] = parcalar[:top_k_per_symbol]
        return gruplar

    def answer(self, query: str, top_k: int | None = None) -> dict:
        """Doğrudan kullanım için: bul ya da 'bulunamadı' söyle. LLM'e ya da
        internete gitmez — yalnızca veritabanını kontrol eder."""
        results = self.retrieve(query, top_k=top_k or settings.rag_top_k)
        if not results:
            return {"found": False, "message": NOT_FOUND_MESSAGE, "results": []}
        return {"found": True, "message": None, "results": results}
