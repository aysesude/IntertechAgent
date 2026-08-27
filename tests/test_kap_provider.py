"""app/providers/kap_p.py: satır normalizasyonu.

Örnek satır UYDURULMADI — 2026-08-24'te gerçek bir `pykap` çağrısıyla elde
edildi (ASELS, get_historical_disclosure_list, 30 günlük pencere). Bu test
o gerçek veri şeklini regresyona karşı kilitler: pykap'ın alan adlarını
değiştirdiği bir sürüm yükseltmesinde sessizce kırılmak yerine burada
patlar.
"""

from datetime import date, datetime

from app.providers.kap_p import satiri_beklenene_cevir, satiri_bildirime_cevir

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


# ---------------------------------------------------------------------------
# Beklenen bildirim (takvim) satırları
# ---------------------------------------------------------------------------

# UYDURMA DEĞİL: 24 Ağustos 2026'da konteyner içinden
# `BISTCompany(ticker="ASELS").get_expected_disclosure_list(count=3)`
# çağrısıyla alınan gerçek satır.
_GERCEK_BEKLENEN_SATIR = {
    "kapTitle": "ASELSAN ELEKTRONİK SANAYİ VE TİCARET A.Ş.",
    "ruleOid": "4028328d55036e0e015505d6bc532eda",
    "ruleTypeTerm": "9 Aylık",
    "startDate": "01.10.2026",
    "endDate": "09.11.2026",
    "stockCode": None,
    "subject": "Finansal Rapor",
    "taxonomyOid": "8a8ae44e49f558ec014a04f3b49d0020",
    "year": 2026,
}


def test_beklenen_bildirim_penceresi_dogru_ayristirilir():
    kayit = satiri_beklenene_cevir("ASELS", _GERCEK_BEKLENEN_SATIR)

    assert kayit.ticker == "ASELS"
    assert kayit.sirket.startswith("ASELSAN")
    assert kayit.konu == "Finansal Rapor"
    assert kayit.donem == "9 Aylık"
    assert kayit.baslangic == date(2026, 10, 1)
    assert kayit.son_tarih == date(2026, 11, 9)


def test_stock_code_null_gelse_de_ticker_korunur():
    """KAP `stockCode` alanını boş dönüyor (ölçüldü); hisse kodu sorguyu
    attığımız ticker'dan taşınmak zorunda, aksi hâlde takvim satırı hangi
    şirkete ait olduğunu söyleyemez."""
    assert _GERCEK_BEKLENEN_SATIR["stockCode"] is None

    kayit = satiri_beklenene_cevir("THYAO", _GERCEK_BEKLENEN_SATIR)

    assert kayit.ticker == "THYAO"


def test_beklenen_bildirimde_bozuk_tarih_none_doner():
    satir = {**_GERCEK_BEKLENEN_SATIR, "endDate": "2026-11-09"}

    kayit = satiri_beklenene_cevir("ASELS", satir)

    # ISO biçimi bu alanda beklenmiyor; ayrıştırılamayan tarih None olur ve
    # sağlayıcı bu kaydı takvimden eler (tarihsiz satır kullanıcıya bir şey
    # söylemez), liste çökmez.
    assert kayit.son_tarih is None
    assert kayit.baslangic == date(2026, 10, 1)


def test_donem_eksikse_none_doner_uydurulmaz():
    satir = {**_GERCEK_BEKLENEN_SATIR, "ruleTypeTerm": None}

    kayit = satiri_beklenene_cevir("ASELS", satir)

    assert kayit.donem is None
    assert kayit.konu == "Finansal Rapor"
