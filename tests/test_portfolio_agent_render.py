"""Portföy Ajanı'nın `_render` yardımcılarının testleri.

NEDEN VAR. `_render_transactions` işlemleri sembol+tür bazında toplulaştırırken
tarihleri atıyordu; "ilk hangisini almışım", "en son ne zaman altın aldım" gibi
sorular cevapsız kalıyordu. Hata canlıda yakalandı çünkü mevcut testler
"ne kadar aldım"ı kapsıyordu, "ne zaman aldım"ı hiç düşünmemişti. Bu dosya o
boşluğu kapatıyor.
"""

from agents.formatting import tr_date
from agents.portfolio_agent import _render, _render_price_history, _render_transactions


def _tx(gun: str, tur: str, sembol, adet, nakit):
    return {
        "transaction_date": f"{gun}T10:00:00+00:00",
        "type": tur,
        "symbol": sembol,
        "quantity": adet,
        "cash_amount_try": nakit,
    }


# Kasıtlı olarak KARIŞIK sırada: servis sıralı döndürse de render'ın kendi
# sıralamasına güvenilmemeli.
ISLEMLER = [
    _tx("2025-09-24", "buy", "TUPRS", 472, -82174.00),
    _tx("2025-08-05", "deposit", None, 0, 1460000.00),
    _tx("2025-09-08", "buy", "TUPRS", 467, -82134.81),
    _tx("2025-09-25", "buy", "GBPTRY", 1029, -43781.64),
]


# ---------------------------------------------------------------------------
# tr_date
# ---------------------------------------------------------------------------


def test_tr_date_iso_tarihi_turkce_bicime_cevirir():
    assert tr_date("2025-09-08T10:00:00+00:00") == "08.09.2025"
    assert tr_date("2025-09-08") == "08.09.2025"


def test_tr_date_cozulemeyen_degeri_uydurmaz():
    # Veri yoksa uzun tire; tarih UYDURULMAZ (formatting.py biçim kararı).
    assert tr_date(None) == "—"
    assert tr_date("") == "—"
    # Ayrıştırılamayan metin olduğu gibi kalır, sahte bir tarihe çevrilmez.
    assert tr_date("bilinmiyor") == "bilinmiyor"


# ---------------------------------------------------------------------------
# _render_transactions — kronoloji
# ---------------------------------------------------------------------------


def test_islemler_ilk_tarihe_gore_siralanir():
    """'İlk hangisini almışım' sorusunun cevabı listenin ilk satırı olmalı."""
    metin = _render_transactions({"transactions": ISLEMLER})
    satirlar = metin.split("\n")[1:]  # başlığı atla

    assert satirlar[0].startswith("NAKİT")  # 05.08.2025 — en eski
    assert satirlar[1].startswith("TUPRS")  # 08.09.2025
    assert satirlar[2].startswith("GBPTRY")  # 25.09.2025


def test_her_satir_ilk_tarihi_tasir():
    metin = _render_transactions({"transactions": ISLEMLER})
    assert "ilk 05.08.2025" in metin
    assert "ilk 08.09.2025" in metin
    assert "ilk 25.09.2025" in metin


def test_tek_islemli_satirda_son_tarih_tekrarlanmaz():
    """Aynı gün tek işlem varsa 'ilk X, son X' yazmak gürültü."""
    metin = _render_transactions({"transactions": [ISLEMLER[3]]})
    assert "ilk 25.09.2025" in metin
    assert "son " not in metin


def test_cok_islemli_satirda_son_tarih_yazilir():
    metin = _render_transactions({"transactions": ISLEMLER})
    # TUPRS iki kez alınmış: 08.09 ve 24.09.
    tuprs = next(s for s in metin.split("\n") if s.startswith("TUPRS"))
    assert "ilk 08.09.2025" in tuprs
    assert "son 24.09.2025" in tuprs


def test_toplamlar_dogru_toplanir():
    tuprs = next(
        s
        for s in _render_transactions({"transactions": ISLEMLER}).split("\n")
        if s.startswith("TUPRS")
    )
    assert "2 alım" in tuprs
    assert "939,00 adet" in tuprs
    # 82.174,00 + 82.134,81
    assert "164.308,81 TL" in tuprs


def test_baslikta_toplam_islem_sayisi_var():
    """'Bu ay kaç işlem yaptım' sorusunda sayı metinde geçmeli; LLM'in
    satırları sayması istenmiyor."""
    metin = _render_transactions({"transactions": ISLEMLER})
    assert metin.startswith("İşlemler (4 işlem")


def test_bos_liste_acik_mesaj_doner():
    assert _render_transactions({"transactions": []}) == "İşlemler: seçilen aralıkta işlem yok."


def test_tarihsiz_satir_render_i_cokertmez():
    """Tarih alanı gelmezse satır yine basılmalı; eksik veri sessizce
    uydurulmaz ama tüm çıktı da kaybedilmez."""
    metin = _render_transactions(
        {"transactions": [{"type": "buy", "symbol": "X", "quantity": 1, "cash_amount_try": -5}]}
    )
    assert "X 1 alım" in metin
    assert "ilk —" in metin


# ---------------------------------------------------------------------------
# _render_price_history
# ---------------------------------------------------------------------------


def test_fiyat_gecmisi_uc_noktalari_ve_degisimi_verir():
    metin = _render_price_history(
        {
            "window": "3m",
            "series": {
                "TUPRS": [
                    {"date": "2026-05-22", "close": 243.10},
                    {"date": "2026-08-20", "close": 391.75},
                ]
            },
        }
    )
    assert "243,10" in metin and "391,75" in metin
    # Değişim kodda hesaplanır, LLM'in seriden yüzde çıkarması istenmez.
    assert "+%61,15" in metin


def test_fiyat_gecmisi_bulunamayan_sembolleri_soyler():
    """Sessizce atlanırsa kullanıcı sorduğu varlığın cevapta olmadığını fark etmez."""
    metin = _render_price_history(
        {
            "window": "3m",
            "series": {"TUPRS": [{"date": "2026-05-22", "close": 243.10}]},
            "unknown_symbols": ["YOKBOYLE"],
            "symbols_without_data": ["OLD"],
        }
    )
    assert "YOKBOYLE" in metin
    assert "OLD" in metin


# ---------------------------------------------------------------------------
# Serbest nakit — anlatıya TUTAR olarak girer
# ---------------------------------------------------------------------------


def test_render_ozette_serbest_nakdi_TUTAR_olarak_yazar():
    """Ölçülen hata (1 Eylül 2026): "Ne kadar param nakitte duruyor?" sorusu
    *"verilerde yer almıyor"* cevabını alıyordu.

    `allocation` nakdi yalnızca YÜZDE dilimi olarak taşıyordu; yüzdeyi toplam
    değerle çarpmak modelin yapması yasak olan bir hesap (sayısal hiçbir değer
    LLM tarafından üretilmez kuralı). Tutarın serileştirmeye girmesi gerekiyor.
    """
    metin = _render(
        {
            "summary": {
                "as_of": "2026-09-01",
                "total_value": 1583703.56,
                "net_invested": 1250000.00,
                "total_cost_basis": 1407837.42,
                "total_gain_loss": {"amount": 333703.56, "percent": 26.70},
                "cash_try": 175866.14,
                "allocation": [{"asset_class": "cash", "percent": 11.10}],
                "holdings_count": 7,
            }
        }
    )

    assert "Serbest nakit: 175.866,14 TL" in metin


def test_render_varlik_listesinde_nakdi_agirligiyla_yazar():
    """Satırların ağırlığı 100'e değil (100 − nakit%) değerine toplanır.

    Nakit yazılmazsa model eksik ağırlığı yorumlamaya çalışıyor; ölçülen
    turda varlık listesi %88,90'da kalıyordu ve fark hiçbir yerde
    açıklanmıyordu.
    """
    metin = _render(
        {
            "holdings": {
                "holdings": [
                    {
                        "symbol": "ASELS",
                        "asset_class": "stock",
                        "quantity": 866,
                        "market_value_try": 348348.50,
                        "weight_percent": 22.00,
                        "unrealized_pnl_percent": 54.84,
                    }
                ],
                "cash_try": 175866.14,
                "cash_weight_percent": 11.10,
            }
        }
    )

    assert "Serbest nakit" in metin
    assert "175.866,14 TL" in metin
    assert "%11,10" in metin


# ---------------------------------------------------------------------------
# Dönem tarihleri — hangi üç ay olduğu yazılmalı
# ---------------------------------------------------------------------------


def test_performansta_DONEM_TARIHLERI_yazilir():
    """21 Ağustos turundan beri açık duran bulgu, 1 Eylül'de yine ölçüldü:
    "Son üç ayda +%5,43 kazandınız" cümlesi hangi üç ayı kastettiğini
    söylemiyordu. Özet skalerleri tarih taşımıyor ve değer serisi anlatıdan
    atılıyor; başlangıç günü atılırken korunmalı."""
    metin = _render(
        {
            "performance": {
                "as_of": "2026-08-31",
                "series_start": "2026-06-02",
                "truncated_to_inception": False,
                "summary": {
                    "change_percent": 5.43,
                    "change_amount": 81629.07,
                    "start_value": 1502074.49,
                    "end_value": 1583703.56,
                },
            }
        }
    )

    assert "Dönem: 02.06.2026 – 31.08.2026" in metin


def test_kirpilmis_pencere_SOYLENIR():
    """ "Yıllık" yazıp dört aylık getiri göstermek kıyası olduğundan iyi ya da
    kötü gösterir."""
    metin = _render(
        {
            "performance": {
                "as_of": "2026-08-31",
                "series_start": "2026-01-27",
                "truncated_to_inception": True,
                "summary": {"change_percent": 26.71},
            }
        }
    )

    assert "portföy bu dönemden genç" in metin


def test_kiyaslamanin_da_donemi_yazilir():
    """Aynı sayfadaki iki yüzde ancak aynı dönemi kapsıyorsa
    karşılaştırılabilir."""
    metin = _render(
        {
            "benchmark": {
                "start_date": "2026-06-02",
                "end_date": "2026-08-31",
                "portfolio_return_percent": 5.43,
                "benchmarks": [{"name": "BIST 100", "return_percent": 4.69}],
            }
        }
    )

    assert "Kıyaslama (02.06.2026 – 31.08.2026)" in metin


def test_nakit_isleminde_ADET_YAZILMAZ():
    """ "1 para yatırma, 0,00 adet, toplam 1.250.000,00 TL" — nakit ayağında
    adet kavramı yok; sıfır bir ölçüm değil, alanın tanımsız olduğunun
    işareti (ölçüldü, 1 Eylül 2026)."""
    metin = _render_transactions(
        {
            "transactions": [
                {
                    "transaction_date": "2025-09-01T10:00:00+00:00",
                    "type": "deposit",
                    "symbol": None,
                    "quantity": 0,
                    "cash_amount_try": 1250000.0,
                }
            ]
        }
    )

    assert "0,00 adet" not in metin
    assert "1.250.000,00 TL" in metin


def test_varlik_isleminde_adet_KORUNUR():
    metin = _render_transactions(
        {
            "transactions": [
                {
                    "transaction_date": "2025-10-23T10:00:00+00:00",
                    "type": "buy",
                    "symbol": "ASELS",
                    "quantity": 866,
                    "cash_amount_try": -224970.45,
                }
            ]
        }
    )

    assert "866,00 adet" in metin
