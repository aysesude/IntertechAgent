"""agents/market_query.py: sorgudan sirket/donem cikarimi.

Bu katman deterministik olmali — LLM yok, tamamen kural tabanli. Yanlis bir
cikarim sessiz bir hataya donusur: filtre yanlis sirkete daralir ve kullaniciya
"bilgi bulunamadi" denir, oysa dogru dokuman veritabaninda durmaktadir.
"""

import pytest

from agents.market_query import donem_tespit_et, filtre_cikar, sirket_tespit_et


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


def test_filtre_cikar_yalnizca_dolu_alanlari_dondurur():
    """Bos degerler sozlukte YER ALMAMALI: cagiran taraf `**filtreler` ile
    aciyor, None gecmek ile hic gecmemek tool tarafinda ayni sey degil."""
    assert filtre_cikar("ASELSAN 2026 2. ceyrek") == {"sirket": "ASELS", "donem": "2026-Q2"}
    assert filtre_cikar("ASELSAN nasil gidiyor") == {"sirket": "ASELS"}
    assert filtre_cikar("enflasyon ne oldu") == {}
