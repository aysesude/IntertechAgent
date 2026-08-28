"""agents/market_agent.py: render fonksiyonları — LLM'den geçmeyen, ham
sunum katmanı (bkz. modül docstring'i: "sayısal hiçbir değer LLM tarafından
üretilmez")."""

from agents.market_agent import _render_hedef_fiyat


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
