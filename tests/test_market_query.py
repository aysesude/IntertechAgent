"""agents/market_query.py: sorgudan sirket/donem cikarimi.

Bu katman deterministik olmali — LLM yok, tamamen kural tabanli. Yanlis bir
cikarim sessiz bir hataya donusur: filtre yanlis sirkete daralir ve kullaniciya
"bilgi bulunamadi" denir, oysa dogru dokuman veritabaninda durmaktadir.
"""

import pytest

from agents.market_query import (
    donem_tespit_et,
    filtre_cikar,
    genel_gundem_istegi_var_mi,
    guncellik_istegi_var_mi,
    sirket_tespit_et,
)


@pytest.mark.parametrize(
    "query, beklenen",
    [
        ("ASELSAN'in son ceyregi nasildi", "ASELS"),
        ("aselsan hakkinda haber var mi", "ASELS"),
        ("Turk Hava Yollari yolcu sayisi", "THYAO"),
        ("THY bilancosu", "THYAO"),
        ("THYAO ne durumda", "THYAO"),
    ],
)
def test_sirket_farkli_yazimlardan_tespit_edilir(query, beklenen):
    assert sirket_tespit_et(query) == beklenen


def test_turkce_karakterli_yazim_da_eslesir():
    """Kullanicilarin cogu Turkce klavye kullanmiyor; iki yazim da ayni koda
    gitmeli, yoksa ayni soru bazen filtreli bazen filtresiz aranir."""
    assert sirket_tespit_et("Türk Hava Yolları") == sirket_tespit_et("Turk Hava Yollari")


def test_uzun_sirket_adi_kisa_olana_tercih_edilir():
    """Esleme dosyasinda hem "garanti bankasi" hem "garan" var; ikisi de ayni
    koda cikmali, kisa olanin once eslesmesi sonucu degistirmemeli."""
    assert sirket_tespit_et("Garanti Bankasi bilancosu") == "GARAN"


def test_sirket_gecmeyen_sorguda_none_doner():
    """Makro sorularda filtre KONULMAMALI: sirket alani bos olan dokumanlar
    (faiz, enflasyon, BIST100) aksi halde elenir."""
    assert sirket_tespit_et("enflasyon rakamlari ne oldu") is None


@pytest.mark.parametrize(
    "query, beklenen",
    [
        ("ASELSAN 2026 2. ceyrek sonuclari", "2026-Q2"),
        ("2026 ikinci ceyrek bilancosu", "2026-Q2"),
        ("2025 dorduncu ceyrek nasildi", "2025-Q4"),
        ("2026 Q3 rakamlari", "2026-Q3"),
        ("2026 ilk ceyrek", "2026-Q1"),
    ],
)
def test_donem_ceyrek_ve_yil_birlikte_yazildiginda_uretilir(query, beklenen):
    assert donem_tespit_et(query) == beklenen


def test_yil_yazilmamissa_donem_uretilmez():
    """Bugunun tarihinden yil tahmin etmiyoruz (CLAUDE.md "Uydurmama"). Yanlis
    tahmin, dogru dokuman veritabaninda dururken "bulunamadi" dedirtir; filtre
    koymamak serbest metin aramasina izin verir."""
    assert donem_tespit_et("son ceyrek nasildi") is None
    assert donem_tespit_et("ikinci ceyrek sonuclari") is None


def test_ceyrek_yazilmamissa_donem_uretilmez():
    assert donem_tespit_et("2026 yilinda ne oldu") is None


@pytest.mark.parametrize(
    "query",
    [
        "ASELSAN'in son bildirimi ne",
        "guncel durum nedir",
        "bugun ne oldu",
        "şimdi fiyat ne kadar",
        "dün ne açıklandı",
        "yeni bir haber var mı",
    ],
)
def test_guncellik_kelimeleri_tespit_edilir(query):
    assert guncellik_istegi_var_mi(query) is True


def test_guncellik_kelimesi_yoksa_false_doner():
    assert guncellik_istegi_var_mi("2026 2. çeyrek net kârı ne kadardı") is False


def test_sonuc_kelimesi_son_ile_sahte_eslesmez():
    """Kelime sınırı olmadan 'son' ARAMASI 'sonuç' icindeki 'son'u da
    yakalar — bu yanlis pozitifi engelliyoruz."""
    assert guncellik_istegi_var_mi("işlem sonucu nedir") is False


def test_haber_kelimesi_guncellik_sayilir():
    """'ASELSAN haberleri neler' sorusu 'son' demeden de bugunu kastediyor.
    Bu kelime guncellik sayilmadiginda soru yalnizca arsive gidiyor ve
    sirketin o gunku KAP bildirimi hic gorunmuyordu."""
    assert guncellik_istegi_var_mi("ASELSAN haberleri neler") is True
    assert guncellik_istegi_var_mi("bu şirketle ilgili bir haber var mı") is True


@pytest.mark.parametrize(
    "query",
    [
        "son piyasa haberleri neler",
        "bugün piyasada ne oldu",
        "gündemde ne var",
        "borsa bugün nasıl",
        "ekonomi haberleri neler",
    ],
)
def test_genel_gundem_istegi_tespit_edilir(query):
    assert genel_gundem_istegi_var_mi(query) is True


@pytest.mark.parametrize(
    "query",
    [
        "portföyüm ne durumda",
        "riskim nedir",
        "2026 2. çeyrek net kârı ne kadardı",
    ],
)
def test_gundem_kelimesi_yoksa_false_doner(query):
    assert genel_gundem_istegi_var_mi(query) is False


def test_gundem_ve_sirket_ayri_sorulardir():
    """Ikisi ayni sorguda da gecebilir ("ASELSAN haberleri"); hangisinin
    kazanacagina market_agent karar verir (sirket varsa KAP). Bu fonksiyon
    yalnizca gundem kelimesinin varligini bildirir, sirkete bakmaz."""
    assert genel_gundem_istegi_var_mi("ASELSAN haberleri neler") is True
    assert sirket_tespit_et("ASELSAN haberleri neler") == "ASELS"


def test_filtre_cikar_yalnizca_dolu_alanlari_dondurur():
    """Bos degerler sozlukte YER ALMAMALI: cagiran taraf `**filtreler` ile
    aciyor, None gecmek ile hic gecmemek tool tarafinda ayni sey degil."""
    assert filtre_cikar("ASELSAN 2026 2. ceyrek") == {"sirket": "ASELS", "donem": "2026-Q2"}
    assert filtre_cikar("ASELSAN nasil gidiyor") == {"sirket": "ASELS"}
    assert filtre_cikar("enflasyon ne oldu") == {}


# ---------------------------------------------------------------------------
# Gundelik kelimeyle cakisan borsa kodlari
# ---------------------------------------------------------------------------


class TestBelirsizTickerlar:
    """BIST 100 eklenince bazi kodlar gundelik Turkce kelimelerle cakisti.

    MAVI (renk), ESEN, EFOR, BERA... Hepsi kucultulup eslestirildiginde
    "grafikteki mavi cizgi" sorgusu Mavi Giyim'e gidiyordu. Ayrica "girisim"
    ve "destek" gibi FINANS KAVRAMLARI da sirket adiyla cakisiyordu —
    "girisim sermayesi nedir" sorusu Girisim Elektrik'e gidiyordu.

    Cozum iki parcali: cakisan tek kelimelik varyantlar eslemeden cikarildi,
    ve borsa kodlari BUYUK HARF DUYARLI taraniyor (kodlar teamulen buyuk
    yazilir).
    """

    def test_kucuk_harf_gundelik_kelime_sirket_sayilmaz(self):
        from agents.market_query import sirket_tespit_et

        for cumle in [
            "Grafikteki mavi çizgi ne anlama geliyor",
            "Esen bir piyasa mı",
            "Bu ay efor sarf ettim",
            "Girişim sermayesi nedir",
            "Destek almak istiyorum",
            "Pasifik okyanusu",
        ]:
            assert sirket_tespit_et(cumle) is None, f"yanlış pozitif: {cumle}"

    def test_BUYUK_harf_ticker_sirkettir(self):
        """Kullanıcı kodu büyük yazdıysa niyeti açıktır."""
        from agents.market_query import sirket_tespit_et

        assert sirket_tespit_et("MAVI hakkında ne biliyorsun") == "MAVI"
        assert sirket_tespit_et("ESEN son çeyrek") == "ESEN"

    def test_tam_ad_her_zaman_calisir(self):
        """Çıkarılan varyantlar tek kelimelikti; tam ad etkilenmedi."""
        from agents.market_query import sirket_tespit_et

        assert sirket_tespit_et("Mavi Giyim son çeyrek") == "MAVI"
        assert sirket_tespit_et("Girişim Elektrik bilançosu") == "GESAN"
        assert sirket_tespit_et("Destek Faktoring") == "DSTKF"

    def test_bist100_sirketleri_taniniyor(self):
        """Eşleme 53 tickerdan 126'ya çıktı; yeni şirketler bulunabilmeli."""
        from agents.market_query import sirket_tespit_et

        assert sirket_tespit_et("Migros bilançosu") == "MGROS"
        assert sirket_tespit_et("Otokar hakkında bilgi") == "OTKAR"
        assert sirket_tespit_et("Kardemir ortaklık yapısı") == "KRDMD"
