"""Fiyat niyeti tespiti — LLM'siz, deterministik.

Bu modülün tek işi, Piyasa Ajanı'nın bir soruyu RAG'e mi yoksa fiyat
tool'larına mı göndereceğine karar vermek. Ölçülen hata (23 Ağustos test
turu): "dolar ne kadar?" sorusu belge aramasına düşüyor ve "veritabanımızda
bu sorguyla ilgili doğrulanmış bir bilgi bulunamadı" dönüyordu — elde güncel
kur dururken.
"""

from agents.price_query import fiyat_niyeti, varlik_tespit_et


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
        assert fiyat_niyeti("Dolar ne kadar?") == {"symbols": ["USDTRY"], "history": False}
        assert fiyat_niyeti("Gram altın kaç TL?") == {"symbols": ["XAUTRY"], "history": False}

    def test_gecmis_sorusu_ayirt_edilir(self):
        # Aynı varlık, FARKLI tool: biri son kapanış, diğeri seri.
        niyet = fiyat_niyeti("XAUTRY'nin son 3 aydaki fiyat geçmişini ver")
        assert niyet == {"symbols": ["XAUTRY"], "history": True}
        assert fiyat_niyeti("Dolar son bir yılda ne yaptı?")["history"] is True

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
