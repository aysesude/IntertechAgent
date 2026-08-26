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
    # "durumda"/"uygulanır" — TFRS/TMS referans dokümanı eklendikten sonra
    # ölçümle doğrulandı: "TMS 29 nedir, hangi durumda uygulanır?" sorgusunda
    # tek ayırt edici kelime "tms" iken ("29" 2 harf olduğu için zaten
    # eleniyor), bu iki jenerik soru-kalıbı kelimesi query_keywords'ün
    # 2/3'ünü oluşturup oranı (1/3) `> 0.5` barajının altına düşürüyordu —
    # doğru dokümanın kendisi havuzda ve mesafe eşiğinin altındaydı ama
    # salt oran yüzünden elendi. "nasıl"/"nedir"/"hangi" gibi zaten var olan
    # soru-kalıbı stopword'leriyle aynı sınıf.
    "durumda",
    "uygulanir",
    # "zaman" ("ne zaman" -> "when") aynı gerekçeyle: kurumsal olaylar
    # tarihçesi turu sonrası ölçümle doğrulandı, "ne" zaten stopword ama
    # "zaman" değildi.
    "zaman",
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
#
# 30'dan 130'a yükseltildi (2026-08-24, temettü geçmişi eklendikten sonra
# ölçüldü): 31 profilin TAMAMINA aynı kalıpta temettü cümlesi eklenince
# aynı sorun çok daha yaygınlaştı — 31 şirketin 12'sinde ("[Şirket]'in
# temettü ödemesi ne kadar" sorgusuyla ölçüldü) kendi dokümanı 30'luk
# havuzun dışında kaldı, en kötü durumda (ARCLK) 108. sırada. Korpus
# toplam ~150 parça olduğu için (küçük, sabit boyutlu bir demo korpusu)
# havuzu neredeyse tüm korpusu kapsayacak şekilde genişletmenin performans
# maliyeti ihmal edilebilir; asıl doğruluk güvencesi zaten mesafe eşiği +
# kelime-örtüşme kapısı, havuz yalnızca "adaya bile giremeden elenme"
# riskini azaltıyor.
_MIN_CANDIDATE_POOL = 130

# Türkçe klavyesi olmayan / aksan girmeyen kullanıcılar için: "FAVOK" ile
# "FAVÖK", "sirket" ile "şirket" aynı kelime sayılsın diye ASCII'ye katlanır.
# "â" da dahildir ("kâr" -> "kar"): eksikliği ölçümle doğrulandı — "kârı"
# hiç foldlanmadığı için "net kârı" gibi hemen her bilanço dokümanında
# geçen evrensel bir ifade, jenerik kelime listesiyle eşleşemeyip uydurma
# şirket sorgularının (ör. "ABC Holding'in ikinci çeyrek net kârı nedir")
# yanlışlıkla "bulundu" sayılmasına katkı sağlıyordu.
_TURKISH_FOLD_MAP = str.maketrans(
    {"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a", "î": "i", "û": "u"}
)


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

# `tur: referans` muafiyeti (bkz. retrieve()) için AYRI, GENEL 0.95 eşiğinden
# ÇOK DAHA SIKI bir mesafe sınırı. Muafiyet ilk eklendiğinde (kelime-örtüşme
# kapısını tamamen atlıyordu) genel 0.95 eşiğiyle çalışıyordu — ama bu, "Altın
# piyasasında ne oluyor?"/"DenizBank hakkında gelişme var mı?"/"Sahte Sanayi
# A.Ş.'nin ortaklık yapısı nedir?" gibi TAMAMEN ALAKASIZ sorularda bile
# referans dokümanlarını (0.51–0.71 mesafe aralığında) "bulundu" saydırıp
# yanlış kaynak listesine sokuyordu (ölçümle doğrulandı, 2026-08-27). Ölçülen
# meşru eşleşmeler ("Konsolide...", "F/K oranı...", "Bedelsiz sermaye
# artırımı...", "TFRS 16 nedir?") hep ≤0.43 mesafede, alakasız sızıntılar hep
# ≥0.51 mesafede kalıyor — aradaki net boşluğa göre eşik seçildi.
_REFERANS_MUAFIYET_MESAFE_ESIGI = 0.47

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
    # "holding"/"enerji" tek başına aşırı jenerik: onlarca `sirket_profili`
    # dokümanında ya şirket adının parçası ("Koç Holding", "Astor Enerji")
    # ya da faaliyet/iştirak alanı olarak geçiyor (ölçümle doğrulandı:
    # "ABC Holding'in ikinci çeyrek net kârı nedir" ve "Falanca Enerji'nin
    # ortaklık yapısı nasıl" gibi uydurma şirket sorguları, salt "holding"/
    # "enerji" kelimeleri üzerinden TAV/Şişecam/Koç/Astor/Tüpraş/Enka gibi
    # tamamen alakasız gerçek şirketlerin verisini "bulundu" saydırdı —
    # uydurma kısım ("ABC", "Falanca") hiç eşleşmemesine rağmen). Gerçek
    # "Koç Holding" / "Astor Enerji" sorguları etkilenmez: o sorgularda
    # "koc"/"astor" gibi ayırt edici bir kelime zaten ayrıca eşleşiyor.
    "holding",
    "enerji",
    # "ikinci çeyrek net kârı" hemen her bilanço dokümanının açılış cümlesi,
    # "ortaklık yapısı" ise hemen her `sirket_profili` dokümanının başlığı.
    # "holding"/"enerji" eklendikten SONRA bile "ABC Holding'in ikinci
    # çeyrek net kârı" ve "Falanca Enerji'nin ortaklık yapısı" sorguları
    # "ikinci"/"net"/"yapisi" tek başına ayırt edici kelime sayıldığı için
    # hâlâ alakasız gerçek şirketleri "bulundu" saydırıyordu (ölçümle
    # doğrulandı). "kari": "â" artık foldlandığı için "kârı" bu köke düşüyor.
    "ikinci",
    "net",
    "kari",
    "yapisi",
    "ortaklik",
    # "temettü" artık 31 `sirket_profili` dokümanının TAMAMINDA geçiyor (her
    # şirkete 2026 temettü/kurumsal olay bilgisi eklendi) — "holding"/
    # "enerji" ile aynı sınıfta jenerik bir kelimeye dönüştü. Eklenmeden
    # önce ölçümle doğrulandı: "XYZ Teknoloji'nin temettüsü ne kadar"
    # sorgusu, "teknoloji" kelimesinin ASTOR dokümanındaki "teknik" ile
    # 4 harflik önek çakışması + "temettüsü"nün ASTOR'un kendi temettü
    # cümlesiyle eşleşmesi yüzünden (2/3 oranı > 0.5) uydurma şirket adı
    # hiç eşleşmemesine rağmen gerçek ASTOR verisini "bulundu" saydırdı.
    "temettu",
    # Temettü paragrafının boyutlu kalıp kelimeleri de aynı gerekçeyle
    # jenerikleştirildi (ölçümle doğrulandı): "ABC Holding'in temettü
    # ödemesi ne kadar" sorgusu "ödemesi" kelimesinin TCELL/EREGL gibi
    # alakasız şirketlerin kendi "ödeme tarihi ..." cümleleriyle eşleşmesi
    # yüzünden yanlış şirket verisini "bulundu" saydırdı; "Falanca
    # Enerji'nin temettü dağıtımı nasıl" sorgusu da benzer şekilde
    # "dağıtımı" kelimesinin ASTOR'daki "dağıtım sistemleri"/"dağıtılmasına
    # karar verildi" ifadeleriyle eşleşmesiyle ASTOR'u yanlışlıkla
    # "bulundu" saydırdı.
    "odeme",
    "dagit",
    # "tarih" (hak kullanım tarihi, ödeme tarihi, kayıt tarihi, kesim
    # tarihi) temettü paragrafının en sık tekrarlanan kelimesi haline geldi
    # — 31 profilin neredeyse tamamında birden fazla kez geçiyor (ölçümle
    # doğrulandı: "Sahte Sanayi'nin temettü dağıtım tarihi nedir" sorgusu,
    # uydurma kısım hiç eşleşmemesine rağmen salt "tarihi" + "temettü" +
    # "dağıtım" kelimeleri üzerinden BIMAS/KCHOL/DOAS/ISCTR/ASTOR gibi
    # tamamen alakasız şirketleri "bulundu" saydırdı).
    "tarih",
    # Temettü cümlesinin geri kalan kalıp kelimeleri de aynı gerekçeyle
    # jenerikleştirildi (ölçümle doğrulandı, 40 uydurma-şirket sorgusundan
    # oluşan bir tarama ile): "2026" ve "yılında" hemen her bilanço/temettü
    # cümlesinde geçen yıl ifadesi; "başına" ("hisse başına brüt/net ...")
    # pay-birimi klişesi. Bunlar tek başına eskiden de jenerikti ama artık
    # temettü/tarih/ödeme/dağıt ile birlikte havuzda ikinci-üçüncü jenerik
    # eşleşme olarak oranı dolduruyor, geriye kalan TEK ayırt edici kelime
    # de (ör. "bankası", "otomotiv") sektör düzeyinde bir kelime olabiliyor
    # ve yine tamamen alakasız gerçek şirketleri "bulundu" saydırıyor.
    "2026",
    "yilinda",
    "yili",
    "basina",
    # "bankası"/"otomotiv" zaten _SIRKET_ALIASES tasarımında "aşırı jenerik"
    # kabul edilip takma ad listesine hiç alınmamıştı (bkz. FROTO/DOAS
    # yorumları) — aynı gerekçe burada da geçerli, iki yerde tutarsız
    # davranmamak için jenerik listeye de eklendi.
    "bankasi",
    "otomotiv",
    # BIST sektör sınıflandırması (ayrı bir turda eklendi) BİRDEN FAZLA
    # şirketin paylaştığı sektörler için de aynı "aşırı jenerik" sorununu
    # taşıyor — ölçümle doğrulandı (40 uydurma-şirket sorgusu taraması):
    # "sanayi" (hem sektör adı hem de "... Sanayi ve Ticaret A.Ş." gibi
    # yaygın bir hukuki ek), "metal" (Metal Ana Sanayi: EREGL+KRDMD),
    # "gıda" (Gıda, İçecek: CCOLA+ULKER) tek başına ayırt edici kelime
    # sayılıp tamamen alakasız uydurma şirket sorgularını gerçek şirket
    # verisiyle eşleştirdi. Yalnızca TEK bir şirkete özgü sektör kelimeleri
    # (ör. "savunma", "inşaat", "imalat") bilinçli olarak burada DEĞİL —
    # bu korpusta hâlâ gerçekten ayırt edici.
    "sanayi",
    "metal",
    "gida",
    "kimya",
    "petrol",
    "plastik",
    "bankacilik",
    "ulastirma",
    "telekomunikasyon",
    "perakende",
    "ticaret",
    "yatirim",
    "gayrimenkul",
    # Kurumsal olaylar tarihçesi turu (2026-08-24) sonrası ölçümle
    # doğrulandı: "halka arz edildi" ifadesi 15'ten fazla profile halka
    # arz tarihi olarak eklenince "halka"/"arz"/"edildi" aynı sınıfta
    # jenerikleşti — "Sahte Sanayi ne zaman halka arz edildi" sorgusu bu
    # üç kelime üzerinden SISE/GARAN/DOAS/KCHOL gibi tamamen alakasız
    # şirketleri "bulundu" saydırdı (uydurma kısım hiç eşleşmemesine
    # rağmen oran 4/6 > 0.5'i geçti). Ayrıca "HALKB" tickerının "halka"
    # ile 4 harflik önek çakışması ayrı bir güvenlik açığıydı — bkz.
    # _SIRKET_ONEK_ISTISNALARI.
    "halka",
    "arz",
    "edildi",
    # Aynı turda "sermaye artırımı" ifadesi 10'dan fazla profile eklendi —
    # ölçümle doğrulandı: "ABC Holding'in sermaye artırımı ne zaman oldu"
    # sorgusu "sermaye"/"artırımı" üzerinden AKBNK/ULKER/TUPRS/ASELS gibi
    # tamamen alakasız şirketleri "bulundu" saydırdı. "bedelsiz"/"birleşme"/
    # "devralma" da aynı turda birden fazla profile eklenen, tek başına
    # ayırt edici olmayan kurumsal-olay klişeleri.
    "sermaye",
    "artirimi",
    "bedelsiz",
    "birlesme",
    "devralma",
    # "satın al-" (M&A anlatımının standart fiili) ve "geçmişi" ("... tarihçesi/
    # geçmişi" başlık kalıbı) aynı turda kanıtlandı: "[Uydurma Şirket] hangi
    # şirketi satın aldı" sorgusu neredeyse HER şirketin M&A cümlesindeki
    # "satın al-" fiili üzerinden rastgele bir gerçek şirketi "bulundu"
    # saydırdı.
    "satin",
    "aldi",
    "gecmisi",
    # "oldu" ("... ne zaman oldu") — jenerik geçmiş zaman soru-kalıbı, "sermaye
    # artırımı ne zaman oldu" gibi sorgularda sermaye/artırımı jenerikleştikten
    # SONRA tek kalan ayırt edici kelime oluyordu.
    "oldu",
    # "Nakit akış tablosu" başlığı ve boilerplate cümlesi 2026-08-26'da 23
    # bilanço dokümanına eklendi — "temettü"/"halka arz" ile aynı sınıfta
    # jenerikleşti. Ölçümle doğrulandı: "BİM'in nakit akış tablosu nasıl?"
    # (BIMAS için bu içerik hiç eklenmedi) sorgusu "nakit"/"akış"/"tablosu"
    # üzerinden YKBNK/GARAN/PGSUS/EKGYO gibi tamamen alakasız şirketleri VE
    # TFRS referans dokümanını "bulundu" saydırıp "Kaynaklar" listesine
    # sokuyordu — cevabın kendisi doğru şekilde "bulunamadı" dese bile.
    "nakit",
    "akis",
    "tablosu",
    # "KAP" (Kamuyu Aydınlatma Platformu) hemen her dokümanın kaynak alanında
    # veya metninde geçiyor — 31 profilin/bilançonun neredeyse tamamı KAP'a
    # atıf yapıyor. "gelişme" de aynı sınıfta genel bir haber/olay kelimesi.
    # Ölçümle doğrulandı (2026-08-26, analist canlı test turu): "KAP'a göre
    # deniz bank hakkında güncel bir gelişme var mı?" sorgusu — DenizBank
    # RAG'da hiç yok — "kap"+"gelişme" üzerinden İş Bankası/Halkbank/Garanti
    # BBVA gibi tamamen alakasız bankaları "bulundu" saydırıp "Kaynaklar"
    # listesine soktu (asıl soru "bilgi yok" dese bile).
    "kap",
    "gelisme",
    # DENENDİ, GERİ ALINDI (2026-08-26): "konsolide"/"finansal" da
    # "Konsolide finansal tablo ne demek?" sorgusunda GARAN/ASELS/BIMAS gibi
    # alakasız şirketleri "bulundu" saydırıp gereksiz kaynak ekliyordu — ama
    # ikisini birden jenerikleştirmek, sorunun asıl doğru cevabını veren
    # TFRS referans dokümanının TEK ayırt edici kelimesini de silip sorguyu
    # tamamen BOŞ sonuca düşürdü (ölçümle doğrulandı). Birkaç fazladan
    # kaynak göstermek, doğru cevabı hiç vermemekten iyidir — bu ikisi
    # BİLEREK jenerik listede DEĞİL.
}


# "altın" (gold, "altin") 4 harflik önekte ("alti") "alt" kökünün HEMEN
# TÜM çekimli hâlleriyle çakışıyor — "altı" (six, "altı aylık"/"ilk altı
# ay" hemen her bilanço dokümanında geçiyor) VE "altında"/"altına"/
# "altından" (below/under — "beklentilerin altında" gibi ifadeler de aynı
# derecede yaygın). Bunlar ayrı ayrı istisna olarak elenemeyecek kadar
# çok ve üretken bir aile (vurgu/hâl ekleriyle çoğalıyor); tek tek
# istisna eklemek yerine "altin" için önek yerine TAM eşleşme zorunlu
# kılındı. Ölçümle doğrulandı (2026-08-26, analist canlı test turu):
# "Altın piyasasında ne oluyor" sorgusu, RAG'da altın fiyatına dair hiç
# içerik olmamasına rağmen ("alti"-önekli çakışma yüzünden) TOASO/SISE
# gibi tamamen alakasız şirketleri "bulundu" saydırıp "Kaynaklar"
# listesine sokuyordu. Şirket adı/ticker çakışmalarıyla aynı sınıf (bkz.
# _SIRKET_ONEK_ISTISNALARI) ama genel kelime düzeyinde.
_TAM_ESLESME_GEREKEN_KELIMELER = {"altin"}


def _query_keyword_matches(qk: str, candidate_keywords: set[str]) -> bool:
    if qk in _TAM_ESLESME_GEREKEN_KELIMELER:
        return qk in candidate_keywords
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


# Bazı tickerlar, kendileriyle anlamsal hiçbir ilgisi olmayan çok yaygın bir
# Türkçe kelimeyle salt 4 harflik önek çakışması yaşıyor. "HALKB" (Halkbank)
# "halka" (kamuya — "halka arz"/"halka açık" ifadelerinde) ile "halk" önekini
# paylaşıyor — ölçümle doğrulandı (2026-08-24, kurumsal olaylar tarihçesi
# turu): "Sahte Sanayi ne zaman halka arz edildi" ve "Ülker ne zaman halka
# arz edildi" gibi sorgular, sorguda Halkbank'a dair hiçbir gerçek referans
# yokken salt bu çakışma yüzünden HALKB'yi "adıyla anıldı" sayıp güvenlik
# ağını (aşağıdaki fonksiyon) yanlışlıkla tetikledi ve tamamen alakasız
# sonuçları öne çıkardı. Bu, "Aselsan"->"ASELS" gibi ANLAMLI önek
# örtüşmelerinden farklı — "halka" hiçbir bağlamda Halkbank'a işaret etmez,
# bu yüzden yalnızca bu ticker için açıkça hariç tutulur.
_SIRKET_ONEK_ISTISNALARI: dict[str, set[str]] = {
    "HALKB": {"halka"},
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
    onek_istisnalari = _SIRKET_ONEK_ISTISNALARI.get(ticker) or set()
    if any(
        qk not in onek_istisnalari and _query_keyword_matches(qk, sirket_keywords)
        for qk in query_keywords
    ):
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

        # Sorgu bir şirketi ADIYLA anıyorsa, O ŞİRKETE ait sonuç kelime-örtüşme
        # oranından MUAFTIR.
        #
        # Oran kapısı alakasız sonuçları elemek için var ve o işi yapıyor; ama
        # kullanıcı elimizde dokümanı bulunan bir şirketi adıyla andığında alaka
        # zaten deterministik olarak kanıtlanmıştır — şirket kodunu sıradan bir
        # kelime gibi saymak yanlıştı. Ölçülen (23 Ağustos test turu):
        #   "ASELS hakkında ne biliyorsun?"          -> 0.50, kural `> 0.5`  ELENDİ
        #   "TUPRS'un bilançosunda öne çıkan ne var?" -> 0.25                 ELENDİ
        # İkisinde de şirket kodu TAM eşleşmişti; eleyen şey sorunun geri
        # kalanındaki konuşma dili ("hakkında", "ne biliyorsun") ve korpusun
        # farklı sözcük seçimiydi — dokümanlar "bilanço" değil "finansal
        # sonuçlar" diyor.
        #
        # Muafiyet DAR: yalnızca kendi `sirket` alanı sorguyla eşleşen sonucu
        # kapsıyor. Başka şirketin dokümanı, alakasız sorgu ve mesafe eşiği
        # aynen eskisi gibi eleniyor.
        # `tur: referans` dokümanları (TFRS/finansal oran/SPK-BDDK/kurumsal
        # olay terimleri sözlüğü — küçük, 4 dokümanlık, şirketten bağımsız
        # bir küme) kelime-örtüşme kapısından DAR bir şekilde muaf: bir
        # kavramı TANIMLAYAN doküman, tanımladığı kelimeleri (ör. "konsolide",
        # "finansal", "tablo") sıkça kullanır — ama bu kelimeler bilanço
        # dokümanlarının boilerplate açılış cümlesinde de geçtiği için jenerik
        # sayılmak zorunda kalıyor (bkz. _GENERIC_FINANCE_TERMS). İkisi
        # çakışınca kavramı tanımlayan TEK doğru kaynak da elenip sorgu
        # tamamen boş dönüyordu (ölçümle doğrulandı: "Konsolide finansal
        # tablo ne demek?" sorgusu). Muafiyet genel 0.95 eşiği yerine ÇOK DAHA
        # SIKI `_REFERANS_MUAFIYET_MESAFE_ESIGI`'ye bağlı: gevşek eşikle
        # tamamen alakasız sorularda bile referans dokümanları "bulundu"
        # saydırıyordu (bkz. o sabitin yorumu). Şirket dokümanlarının aksine
        # burada "yanlış şirket" riski yok, yalnızca "alakasızlık" riski var —
        # sıkı mesafe eşiği onu da kapatıyor.
        filtered = [
            r
            for r in results
            if r.get("distance", 1.0) <= settings.rag_distance_threshold
            and (
                _shares_a_keyword(query_keywords, _result_keywords(r))
                or _sirket_matches_query(r, query_keywords)
                or (
                    (r.get("metadata") or {}).get("tur") == "referans"
                    and r.get("distance", 1.0) <= _REFERANS_MUAFIYET_MESAFE_ESIGI
                )
            )
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
