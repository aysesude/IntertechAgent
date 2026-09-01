"""agents/market_agent.py: LLM'den geçmeyen, saf/kural tabanlı yardımcı
fonksiyonlar — render katmanı ve filtresiz-yedek-arama güvenlik ağı.
"""

from agents.market_agent import (
    _render_hedef_fiyat,
    _render_temel_oranlar,
    _yanlis_sirket_sonuclarini_ele,
)


def test_render_hedef_fiyat_tek_kayit():
    data = {
        "records": [
            {
                "symbol": "GARAN",
                "institution": "Şeker Yatırım",
                "recommendation": "AL",
                "target_price": 182.99,
                "currency": "TRY",
                "price_at_report": 133.00,
                "previous_target_price": None,
                "revision_direction": None,
                "horizon_months": None,
                "report_date": "2026-08-28",
                "source_url": "https://www.sekeryatirim.com.tr/Arastirma/TavsiyeListesi",
            }
        ],
        "unknown_symbols": [],
        "symbols_without_data": [],
    }
    metin = _render_hedef_fiyat(data)
    assert "GARAN" in metin
    assert "Şeker Yatırım" in metin
    assert "AL" in metin
    assert "182,99" in metin
    assert "28.08.2026" in metin
    # Rapor anındaki fiyat da (kaynağın kendi bağlamı için) gösterilmeli.
    assert "133,00" in metin


def test_render_hedef_fiyat_revizyon_yonu_gosterilir():
    """Önceki hedeften farklıysa yön ("yükseltildi"/"düşürüldü") ve eski
    değer görünmeli — doküman "hedef yükseltildi mi düşürüldü mü" sorusunun
    hedefin kendisinden daha bilgilendirici olduğunu söylüyor."""
    data = {
        "records": [
            {
                "symbol": "ASELS",
                "institution": "Şeker Yatırım",
                "recommendation": "AL",
                "target_price": 495.00,
                "currency": "TRY",
                "price_at_report": 403.75,
                "previous_target_price": 450.00,
                "revision_direction": "yukseltme",
                "horizon_months": None,
                "report_date": "2026-08-28",
                "source_url": "https://example.com",
            }
        ],
        "unknown_symbols": [],
        "symbols_without_data": [],
    }
    metin = _render_hedef_fiyat(data)
    assert "yükseltildi" in metin
    assert "450,00" in metin


def test_render_hedef_fiyat_bulunamayan_sembol_belirtilir():
    """Kayıt yoksa uydurma yapılmaz — hangi sembollerin bulunamadığı açıkça
    belirtilir (CLAUDE.md "Uydurmama")."""
    data = {"records": [], "unknown_symbols": ["XYZ"], "symbols_without_data": ["ZOREN"]}
    metin = _render_hedef_fiyat(data)
    assert "XYZ" in metin
    assert "ZOREN" in metin


def test_render_hedef_fiyat_bos_veri():
    assert _render_hedef_fiyat(
        {"records": [], "unknown_symbols": [], "symbols_without_data": []}
    ) == ("Hedef fiyat: istenen varlık için kayıt yok.")


# ---------------------------------------------------------------------------
# _yanlis_sirket_sonuclarini_ele — filtresiz yedek aramanın çapraz-şirket
# güvenlik ağı.
#
# 2026-08-27, analist test turunda ölçülen bir hatayı önlüyor: "İş Bankası'nın
# kurucusu kimdir" sorusu, RAG'de İş Bankası için yeterli doküman olmadığından
# `execute()`'un filtresiz yedek aramasına düşmüş ve retriever'ın mesafe+
# kelime-örtüşme eşiği (LEKSİK, şirket kimliğine değil) "kurucu" kelimesini
# paylaştığı için ASELSAN'ın kuruluş belgesini yanlışlıkla "ilgili" sayıp
# cevap diye sunmuştu (bkz. _yanlis_sirket_sonuclarini_ele docstring'i,
# agents/market_agent.py).
# ---------------------------------------------------------------------------


def _parca(sirket: str | None, baslik: str = "belge") -> dict:
    return {"content": "...", "metadata": {"sirket": sirket, "baslik": baslik}}


def test_dogru_sirketin_sonuclari_dokunulmadan_kalir():
    sonuclar = [_parca("ASELS"), _parca("ASELS")]
    assert _yanlis_sirket_sonuclarini_ele(sonuclar, "ASELS") == sonuclar


def test_baska_sirketin_sonucu_elenir():
    """Regresyon: "İş Bankası'nın kurucusu kimdir" sorusu ASELSAN'ın kuruluş
    belgesini döndürmüştü (ölçüldü, 2026-08-27)."""
    sonuclar = [_parca("ASELS", "ASELSAN Kuruluş Bilgisi")]
    assert _yanlis_sirket_sonuclarini_ele(sonuclar, "ISCTR") == []


def test_sirketsiz_genel_belgeler_dokunulmadan_kalir():
    """`sirket` alanı boş (makro/genel) parçalar başka bir şirketin dokümanı
    DEĞİLDİR, elenmemeli — yalnızca FARKLI bir şirkete ait parçalar elenir."""
    genel = _parca(None, "Enflasyon Raporu")
    assert _yanlis_sirket_sonuclarini_ele([genel], "ISCTR") == [genel]


def test_karisik_sonuclarda_yalnizca_yanlis_sirket_elenir():
    dogru = _parca("ISCTR", "İş Bankası Şirket Profili")
    yanlis = _parca("ASELS", "ASELSAN Kuruluş Bilgisi")
    genel = _parca(None, "BIST 100 Genel Görünüm")
    assert _yanlis_sirket_sonuclarini_ele([dogru, yanlis, genel], "ISCTR") == [dogru, genel]


def test_bos_liste_bos_doner():
    assert _yanlis_sirket_sonuclarini_ele([], "ISCTR") == []


# ---------------------------------------------------------------------------
# Değerleme çarpanları (F/K, PD/DD) — RAG'e gitmez
# ---------------------------------------------------------------------------


def test_temel_oran_render_YFINANCE_sozlesmesine_uyar():
    """Ölçüldü (yfinance 1.6.0): `profitMargins` KESİR (0,2949),
    `dividendYield` ZATEN YÜZDE (3,06). İkisine aynı işlemi uygulamak sayıyı
    yüz kat yanlış gösterirdi."""
    metin = _render_temel_oranlar(
        "AKBNK",
        {
            "records": {
                "AKBNK": {
                    "trailingPE": 5.6074767,
                    "forwardPE": 4.1189933,
                    "priceToBook": 1.1527562,
                    "ebitdaMargins": 0.0,
                    "profitMargins": 0.29490998,
                    "dividendYield": 3.06,
                    "marketCap": 374399991808,
                    "currency": "TRY",
                }
            },
            "symbols_without_data": [],
            "source": "yfinance",
            "fetched_at": "2026-09-01T17:30:00+00:00",
        },
    )

    assert "F/K: 5,61" in metin
    assert "PD/DD: 1,15" in metin
    assert "Kâr marjı: %29,49" in metin
    assert "Temettü verimi: %3,06" in metin
    # Bankada FAVÖK tanımsız; yfinance 0 döner. "%0,00" basmak bir ÖLÇÜM
    # iddiası olurdu — o oranın o şirket için anlamı yok.
    assert "FAVÖK" not in metin
    # Kaynak + tarih HER ZAMAN yazılır (AK 5.3).
    assert "yfinance" in metin and "01.09.2026" in metin
    # Büyük tutar okunur ölçekte.
    assert "374,40 milyar TRY" in metin


def test_temel_oran_veri_yoksa_UYDURMAZ():
    metin = _render_temel_oranlar("ZZZZ", {"records": {}, "symbols_without_data": ["ZZZZ"]})

    assert "bulunamadı" in metin
    assert "ZZZZ" in metin
