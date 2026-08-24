"""app/providers/kap_p.py: satır normalizasyonu.

Örnek satır UYDURULMADI — 2026-08-24'te gerçek bir `pykap` çağrısıyla elde
edildi (ASELS, get_historical_disclosure_list, 30 günlük pencere). Bu test
o gerçek veri şeklini regresyona karşı kilitler: pykap'ın alan adlarını
değiştirdiği bir sürüm yükseltmesinde sessizce kırılmak yerine burada
patlar.
"""

from datetime import datetime

from app.providers.kap_p import satiri_bildirime_cevir

# Gerçek `get_historical_disclosure_list` çıktısından birebir (ölçümle).
_GERCEK_ORNEK_SATIR = {
    "publishDate": "04.08.2026 18:39:41",
    "fundCode": None,
    "kapTitle": "ASELSAN ELEKTRONİK SANAYİ VE TİCARET A.Ş.",
    "isOldKap": False,
    "disclosureClass": "FR",
    "disclosureType": "FR",
    "disclosureCategory": "FR",
    "summary": None,
    "subject": "Finansal Rapor",
    "relatedStocks": None,
    "year": 2026,
    "ruleType": "6 Aylık",
    "period": 2,
    "disclosureIndex": 1643141,
    "isLate": False,
    "stockCodes": "ASELS",
    "hasMultiLanguageSupport": True,
    "attachmentCount": 2,
    "modifyStatus": None,
}


def test_gercek_ornek_satir_dogru_ayristirilir():
    bildirim = satiri_bildirime_cevir("ASELS", _GERCEK_ORNEK_SATIR)

    assert bildirim.ticker == "ASELS"
    assert bildirim.baslik == "Finansal Rapor (6 Aylık)"
    assert bildirim.tarih == datetime(2026, 8, 4, 18, 39, 41)
    assert bildirim.url == "https://www.kap.org.tr/tr/Bildirim/1643141"
    assert bildirim.ham == _GERCEK_ORNEK_SATIR


def test_ruleType_eksikse_baslik_tek_basina_kalir():
    """Bazı bildirim türlerinde donem bilgisi olmayabilir (ör. genel
    duyurular); başlık jenerik ama boş kalmamalı."""
    satir = {**_GERCEK_ORNEK_SATIR, "ruleType": None}
    bildirim = satiri_bildirime_cevir("ASELS", satir)
    assert bildirim.baslik == "Finansal Rapor"


def test_subject_eksikse_yerine_gecen_metin_kullanilir():
    satir = {**_GERCEK_ORNEK_SATIR, "subject": None, "ruleType": None}
    bildirim = satiri_bildirime_cevir("ASELS", satir)
    assert bildirim.baslik == "Başlıksız bildirim"


def test_bozuk_tarih_formati_none_doner_istisna_firlatmaz():
    """pykap sürüm değiştirip biçimi bozarsa (ör. ISO 8601'e geçerse) tüm
    bildirim listesi çökmemeli — o kaydın tarihi None olur, geri kalan
    alanlar (başlık, url) korunur."""
    satir = {**_GERCEK_ORNEK_SATIR, "publishDate": "2026-08-04T18:39:41Z"}
    bildirim = satiri_bildirime_cevir("ASELS", satir)
    assert bildirim.tarih is None
    assert bildirim.url == "https://www.kap.org.tr/tr/Bildirim/1643141"


def test_disclosure_index_eksikse_url_none_doner():
    satir = {**_GERCEK_ORNEK_SATIR, "disclosureIndex": None}
    bildirim = satiri_bildirime_cevir("ASELS", satir)
    assert bildirim.url is None
