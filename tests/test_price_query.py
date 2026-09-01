"""Fiyat niyeti tespiti — LLM'siz, deterministik.

Bu modülün tek işi, Piyasa Ajanı'nın bir soruyu RAG'e mi yoksa fiyat
tool'larına mı göndereceğine karar vermek. Ölçülen hata (23 Ağustos test
turu): "dolar ne kadar?" sorusu belge aramasına düşüyor ve "veritabanımızda
bu sorguyla ilgili doğrulanmış bir bilgi bulunamadı" dönüyordu — elde güncel
kur dururken.
"""

from agents.price_query import fiyat_niyeti, uygunluk_niyeti, varlik_tespit_et


class TestVarlikTespiti:
    def test_dogal_dildeki_adlari_sembole_cevirir(self):
        assert varlik_tespit_et("dolar ne kadar") == ["USDTRY"]
        assert varlik_tespit_et("euro kuru") == ["EURTRY"]
        assert varlik_tespit_et("gram altın fiyatı") == ["XAUTRY"]

    def test_altin_tek_basina_GRAM_altindir(self):
        # Piyasa teamülü: "altın 2.300 TL" denince gram altın kastedilir.
        assert varlik_tespit_et("altın ne kadar") == ["XAUTRY"]

    def test_SPESIFIK_ad_genel_adi_yener(self):
        # "çeyrek altın" içinde "altın" da geçiyor. Genel ad kazansaydı
        # çeyrek altın soran kullanıcıya GRAM altın fiyatı dönerdi.
        assert varlik_tespit_et("çeyrek altın ne kadar") == ["CEYREK"]
        assert varlik_tespit_et("tam altın kaç TL") == ["TAMALTIN"]

    def test_tek_basina_CEYREK_varlik_sayilmaz(self):
        """Finansal dilde "çeyrek" ağırlıklı olarak yılın çeyreğidir.

        Takma ad listesine tek başına girseydi "2. çeyrek net kârı ne kadar?"
        sorusu çeyrek altın fiyatı sorgusuna dönüşür ve çalışan bilanço yolu
        bozulurdu.
        """
        assert varlik_tespit_et("2. çeyrek net kârı") == []

    def test_sembolun_kendisi_de_taninir(self):
        assert varlik_tespit_et("THYAO fiyatı") == ["THYAO"]
        assert varlik_tespit_et("XAUTRY ne durumda") == ["XAUTRY"]

    def test_birden_fazla_varlik_sirasiyla_doner(self):
        sonuc = varlik_tespit_et("dolar ve euro ne kadar")
        assert sonuc == ["USDTRY", "EURTRY"]

    def test_varlik_yoksa_bos_doner(self):
        assert varlik_tespit_et("portföyüm ne durumda") == []


class TestFiyatNiyeti:
    def test_guncel_fiyat_sorusu(self):
        assert fiyat_niyeti("Dolar ne kadar?") == {
            "symbols": ["USDTRY"],
            "history": False,
            "window": None,
        }
        assert fiyat_niyeti("Gram altın kaç TL?") == {
            "symbols": ["XAUTRY"],
            "history": False,
            "window": None,
        }

    def test_gecmis_sorusu_ayirt_edilir(self):
        # Aynı varlık, FARKLI tool: biri son kapanış, diğeri seri.
        niyet = fiyat_niyeti("XAUTRY'nin son 3 aydaki fiyat geçmişini ver")
        assert niyet == {"symbols": ["XAUTRY"], "history": True, "window": "3m"}
        assert fiyat_niyeti("Dolar son bir yılda ne yaptı?")["history"] is True

    def test_araya_sayi_giren_sure_kaliplari_da_gecmis_sayilir(self):
        """ "son ay"/"son bir yıl" gibi sabit kalıplar araya bir SAYI
        girdiğinde ("son 1 ayda") eşleşmiyordu (ölçümle doğrulandı,
        2026-08-26): neredeyse aynı anlama gelen "altın yükseldi mi son bir
        ayda" doğru şekilde geçmiş sayılırken "altın nasıl bir yükseklik
        gösterdi son 1 ayda" RAG'a düşüp başarısız oluyordu."""
        assert fiyat_niyeti("altın nasıl bir yükseklik gösterdi son 1 ayda") == {
            "symbols": ["XAUTRY"],
            "history": True,
            "window": "1m",
        }
        assert fiyat_niyeti("dolar son 6 ayda nasıl gitti")["window"] == "6m"
        assert fiyat_niyeti("gümüş son 2 haftada ne oldu")["window"] == "1m"

    def test_icerik_sorusu_bilanco_kalemi_gecince_fiyat_sayilmaz(self):
        """Sorguda bir BIST ticker'ı ("ARCLK", "PGSUS", "KCHOL" gibi kodun
        kendisi) VE "ne kadar" birlikte geçince bu tek başına PİYASA FİYATI
        sanılıyordu (ölçümle doğrulandı, 2026-08-26): "ARCLK'nin serbest
        nakit akışı ne kadar?" ve "PGSUS'un brüt kârı ne kadar oldu?" gibi
        RAG'daki bilanço içeriğiyle yanıtlanması gereken sorular fiyat/
        tarihçe tool'una yönlendirilip "kayıt bulunamadı" ya da alakasız
        güncel fiyat döndürüyordu."""
        assert fiyat_niyeti("ARCLK'nin serbest nakit akışı ne kadar?") is None
        assert fiyat_niyeti("PGSUS'un brüt kârı ne kadar oldu?") is None
        assert fiyat_niyeti("KCHOL'un FAVÖK marjı ne kadar?") is None
        assert fiyat_niyeti("AKBNK'nin nakit akış tablosu nasıl?") is None

    def test_icerik_sorusu_disinda_ticker_fiyat_sorgusu_bozulmaz(self):
        """Düzeltme kapıyı kapatmamalı: ticker + "ne kadar" gerçek bir fiyat
        sorusuysa (bilanço kalemi kelimesi geçmiyorsa) hâlâ fiyat tool'una
        gitmeli."""
        assert fiyat_niyeti("ARCLK ne kadar?") == {
            "symbols": ["ARCLK"],
            "history": False,
            "window": None,
        }
        assert fiyat_niyeti("THYAO fiyatı ne kadar?") == {
            "symbols": ["THYAO"],
            "history": False,
            "window": None,
        }

    def test_iki_sart_birlikte_aranir(self):
        """Tek başına fiyat kalıbı ya da tek başına varlık adı YETMEZ."""
        # Fiyat kalıbı var, varlık yok -> portföy sorusu olabilir.
        assert fiyat_niyeti("Portföyüm ne kadar?") is None
        # Varlık var, fiyat kalıbı yok -> haber sorusu olabilir.
        assert fiyat_niyeti("Dolar hakkındaki son haberler neler?") is None

    def test_haber_ve_bilanco_sorulari_RAG_yolunda_kalir(self):
        """Yanlış dallanma, çalışan RAG yolunu bozmak demek olurdu."""
        assert fiyat_niyeti("Aselsan haberleri neler?") is None
        assert fiyat_niyeti("Bankacılık sektöründe son durum ne?") is None
        assert fiyat_niyeti("Akbank'ın 2. çeyrek net kârı ne kadar?") is None

    def test_risk_ve_portfoy_sorulari_etkilenmez(self):
        assert fiyat_niyeti("Riskim nedir?") is None
        assert fiyat_niyeti("Hangi varlıklara sahibim?") is None


class TestYabanciHisseler:
    """ABD hisseleri evrene girdi (21 sembol, USD).

    Türk kullanıcı bunları koduyla değil ADIYLA yazıyor ("apple hissesi ne
    kadar"), oysa `company_mappings.json` yalnızca yerli şirketleri tanıyor
    ve zaten RAG filtresi içindir. Bu yüzden yabancı şirket adları
    `_TAKMA_ADLAR`'a eklendi.
    """

    def test_sirket_adiyla_bulunur(self):
        assert fiyat_niyeti("Apple hissesi ne kadar?") == {
            "symbols": ["AAPL"],
            "history": False,
            "window": None,
        }
        assert fiyat_niyeti("Coca cola hisse fiyatı nedir?") == {
            "symbols": ["KO"],
            "history": False,
            "window": None,
        }

    def test_sembolun_kendisiyle_de_bulunur(self):
        assert fiyat_niyeti("TSLA fiyatı nedir?") == {
            "symbols": ["TSLA"],
            "history": False,
            "window": None,
        }
        # Tire içeren tek sembol; kelime sınırı regex'i onu bölmemeli.
        assert fiyat_niyeti("BRK-B ne kadar?") == {
            "symbols": ["BRK-B"],
            "history": False,
            "window": None,
        }

    def test_gecmis_yolu_yabancida_da_calisir(self):
        assert fiyat_niyeti("NVDA son 3 ayda ne yaptı?")["history"] is True


class TestBuyukHarfDuyarliSemboller:
    """`V` ve `META` yalnızca BÜYÜK harfle çıplak eşleşir.

    İkisi de küçültülünce gündelik Türkçeyle çakışıyor: `V` tek harf,
    `meta` ise finans Türkçesinde "emtia" demek. Küçük harfli tarama
    bırakılsaydı "meta fiyatları arttı mı" sorusu Meta Platforms fiyat
    sorgusuna dönerdi.
    """

    def test_kucuk_harfli_gundelik_kullanim_tetiklemez(self):
        assert fiyat_niyeti("Meta fiyatları bu ay arttı mı?") is None

    def test_buyuk_harfli_sembol_calisir(self):
        assert fiyat_niyeti("META hissesi ne kadar?") == {
            "symbols": ["META"],
            "history": False,
            "window": None,
        }
        assert fiyat_niyeti("V hissesi ne kadar?") == {
            "symbols": ["V"],
            "history": False,
            "window": None,
        }

    def test_takma_ad_her_yazimda_erisim_birakir(self):
        """Kısıtlama erişimi KAPATMAMALI: şirket adı hâlâ her yazımda bulur."""
        assert fiyat_niyeti("visa ne kadar?") == {
            "symbols": ["V"],
            "history": False,
            "window": None,
        }
        assert fiyat_niyeti("facebook hissesi kaç dolar?") == {
            "symbols": ["META"],
            "history": False,
            "window": None,
        }


def test_kac_dolar_kaliba_dahil_ama_kur_sorgusu_uretmez():
    """ "X kaç dolar?" — ABD hisseleriyle birlikte doğal hâle gelen kalıp.

    Tuzak: kalıbın içindeki "dolar" USDTRY takma adıdır. Silinmeseydi
    kullanıcı hisse sorarken cevaba kur da eklenirdi.
    """
    assert fiyat_niyeti("AAPL kaç dolar?") == {
        "symbols": ["AAPL"],
        "history": False,
        "window": None,
    }
    # Gerçek kur sorusu bozulmamalı.
    assert fiyat_niyeti("Dolar kaç TL?") == {
        "symbols": ["USDTRY"],
        "history": False,
        "window": None,
    }


class TestHedefFiyatNiyeti:
    """Hedef fiyat (analist tavsiyesi) sorguları — target_prices tablosuna
    gider, RAG'a ya da güncel fiyat yoluna DEĞİL (bkz.
    app/services/target_price_ingest.py docstring'i: neden RAG değil)."""

    def test_sirket_ile_birlikte_ticker_dondurur(self):
        from agents.price_query import hedef_fiyat_niyeti

        assert hedef_fiyat_niyeti("GARAN'ın hedef fiyatı ne?") == "GARAN"
        assert hedef_fiyat_niyeti("ASELS için analist tavsiyesi ne?") == "ASELS"

    def test_kalip_yoksa_none_doner(self):
        from agents.price_query import hedef_fiyat_niyeti

        assert hedef_fiyat_niyeti("GARAN'ın fiyatı ne kadar?") is None

    def test_sirket_tespit_edilemezse_none_doner(self):
        """Kalıp geçse bile şirket tespit edilemezse (genel bir kavram
        sorusu) None döner — uydurma şirket varsayılmaz."""
        from agents.price_query import hedef_fiyat_niyeti

        assert hedef_fiyat_niyeti("Hedef fiyatlar nasıl belirlenir?") is None

    def test_fiyat_niyeti_hedef_fiyat_sorusunu_kapsamiyor(self):
        """fiyat_niyeti() bu sorguları kendi kapsamı dışında bırakmalı ki
        market_agent hedef_fiyat_niyeti()'ni önce kontrol edebilsin —
        ikisi çakışırsa güncel fiyat yolu (yanlışlıkla) kazanırdı."""
        assert fiyat_niyeti("GARAN'ın hedef fiyatı ne?") is None
        assert fiyat_niyeti("ASELS için analist tavsiyesi ne?") is None


# ---------------------------------------------------------------------------
# Endeksler — fiyatlanıyor ama satın alınamıyor
# ---------------------------------------------------------------------------


def test_ENDEKS_sorulari_fiyat_yoluna_gider():
    """`tradable=False` bir ALIM kısıtıdır, fiyat sorgusu kısıtı değil.

    Ölçüldü (1 Eylül 2026 sohbet turu): "BIST bugün nasıl?" ve "S&P 500 ne
    durumda?" belge aramasına düşüp *"veritabanımızda bu sorguyla ilgili
    doğrulanmış bir bilgi bulunamadı"* cevabı alıyordu — aynı oturumda
    Analist Ajanı XU100 serisini sorunsuz kullanırken. Endeksin kaç puan
    olduğu meşru bir sorudur ve verisi elimizde.
    """
    for soru, beklenen in (
        ("BIST bugün nasıl?", "XU100"),
        ("BIST 100 kaç puan?", "XU100"),
        ("Borsa İstanbul ne durumda?", "XU100"),
        ("S&P 500 ne durumda?", "SPX"),
    ):
        niyet = fiyat_niyeti(soru)
        assert niyet is not None, f"{soru!r} fiyat yoluna girmedi"
        assert niyet["symbols"] == [beklenen], soru


def test_endeks_kaliplari_ICERIK_sorusunu_yutmaz():
    """ "ne durumda" gibi genel kalıplar eklendi; bilanço/finansal tablo
    soruları yine RAG'de kalmalı (`_ICERIK_KELIMELERI_RE` önceliği)."""
    assert fiyat_niyeti("Aselsan bilançosu nasıl?") is None
    assert fiyat_niyeti("Tüpraş'ın 2. çeyrek net kârı ne kadar?") is None
    assert fiyat_niyeti("Borsa saat kaçta kapanır?") is None
    # Varlık adı geçmeyen genel soru fiyat sorgusu değildir.
    assert fiyat_niyeti("Portföyüm ne durumda?") is None


# ---------------------------------------------------------------------------
# Zaman penceresi — sorulan dönem tool'a geçmeli
# ---------------------------------------------------------------------------


def test_SORULAN_PENCERE_niyete_girer():
    """Ölçüldü (1 Eylül 2026): "Dolar son bir yılda ne yaptı?" sorusu
    pencere GEÇİRMEDEN gidiyordu; tool varsayılanı 3 ay olduğu için cevap
    *"son bir yıllık performansı bulunmuyor"* deyip 3 aylık veriyi
    veriyordu — bir yıllık seri veritabanında dururken."""
    assert fiyat_niyeti("Dolar son bir yılda ne yaptı?")["window"] == "12m"
    assert fiyat_niyeti("Altın son 3 ayda ne yaptı?")["window"] == "3m"
    assert fiyat_niyeti("Dolar son 1 ayda yükseldi mi?")["window"] == "1m"
    assert fiyat_niyeti("Altın yılbaşından beri ne yaptı?")["window"] == "ytd"


def test_ara_deger_UST_pencereye_yuvarlanir():
    """ "Son 9 ay" diye bir pencere yok. Kullanıcının istediğinden KISA bir
    pencere göstermek sorulan soruyu cevaplamamak olur; üste yuvarlanır."""
    assert fiyat_niyeti("Altın son 9 ayda ne yaptı?")["window"] == "12m"
    assert fiyat_niyeti("Dolar son 2 ayda ne yaptı?")["window"] == "3m"


def test_guncel_fiyat_sorusunda_pencere_YOK():
    """Pencere yalnızca geçmiş sorgusunda anlamlı."""
    niyet = fiyat_niyeti("Dolar ne kadar?")

    assert niyet["history"] is False
    assert niyet["window"] is None


# ---------------------------------------------------------------------------
# "Bunu alabilir miyim?" — uygunluk sorusu
# ---------------------------------------------------------------------------


def test_uygunluk_sorusu_varligi_tespit_eder():
    """Ölçüldü (1 Eylül 2026): "Serbest fon alabilir miyim?" ve "BIST 100
    endeksinden alabilir miyim?" Web Araştırma Ajanı'na düşüp ansiklopedik
    cevap aldı — oysa doğru cevap sistemin kendi verisinde (puan 6, serbest
    fon seviye 7)."""
    assert uygunluk_niyeti("Serbest fon alabilir miyim?") == "BHE"
    assert uygunluk_niyeti("BIST 100 endeksinden alabilir miyim?") == "XU100"
    assert uygunluk_niyeti("Para piyasası fonu bana uygun mu?") == "IOO"
    assert uygunluk_niyeti("Apple hissesi alabilir miyim?") == "AAPL"


def test_uygunluk_sorusu_belirsizse_UYDURMAZ():
    """ "Fon alabilir miyim?" hangi fonu kastettiğini söylemiyor; uydurma bir
    sembol seçmek yanlış cevap üretirdi."""
    assert uygunluk_niyeti("Fon alabilir miyim?") is None
    # Uygunluk kalıbı yoksa bu yola hiç girilmez.
    assert uygunluk_niyeti("Serbest fon nedir?") is None
    assert uygunluk_niyeti("Dolar ne kadar?") is None
