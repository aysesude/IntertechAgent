"""Portföy Ajanı'nın profil-uygunluk bilgilendirmesi testleri.

NEDEN VAR. Bu, "risk analizi" DEĞİLDİR (o `agents/risk_agent.py`'nin işi) —
kullanıcının GÜNCEL elinde olan ama GÜNCEL anket puanının artık izin
vermediği varlık sınıflarının basit bir bildirimi (bkz. `agents/
portfolio_agent.py` modül docstring'i "2026-08-28 eki",
`app/services/advice_eligibility.mismatched_asset_classes`). `risk_agent`
yalnızca kullanıcı "ne yapmalıyım" tarzı bir soru sorduğunda çalıştığı için
bu bilgi, olmasaydı, "portföyümü göster" gibi en sıradan bir soruda hiç
görünmezdi — bu dosya o boşluğu kapatan `_profil_uyum_disi_siniflar`/
`_render` mantığını test eder.

Saf fonksiyon testleri gerçek bir MCP çağrısı YAPMAZ (bkz. `_fetch_risk_
survey_score`, o ayrı bir entegrasyon testinde — tests/
test_portfolio_agent_tools.py — ele alınır)."""

from agents.portfolio_agent import _profil_uyum_disi_siniflar, _render

# ---------------------------------------------------------------------------
# _profil_uyum_disi_siniflar
# ---------------------------------------------------------------------------


def test_uyumsuzluk_yok_tum_sinif_izinli():
    """Puan=7 (AGGRESSIVE) her sınıfa izin verir; hiçbir uyumsuzluk olmaz."""
    holdings_data = {
        "holdings": [{"symbol": "TST", "asset_class": "stock", "weight_percent": 100.0}]
    }

    assert _profil_uyum_disi_siniflar(holdings_data, 7) == []


def test_uyumsuzluk_var():
    """Puan=3 (BALANCED) STOCK'a (seviye 5) izin vermez; elde STOCK varsa
    bu, bildirilmesi gereken bir uyumsuzluktur."""
    holdings_data = {
        "holdings": [{"symbol": "TST", "asset_class": "stock", "weight_percent": 100.0}]
    }

    assert _profil_uyum_disi_siniflar(holdings_data, 3) == ["stock"]


def test_anket_bossa_kontrol_atlanir():
    """`risk_survey_score=None` (anket hiç doldurulmamış) — uydurma yok,
    kontrol tamamen atlanır."""
    holdings_data = {
        "holdings": [{"symbol": "TST", "asset_class": "stock", "weight_percent": 100.0}]
    }

    assert _profil_uyum_disi_siniflar(holdings_data, None) == []


def test_fiyati_eksik_varlik_elde_sayilmaz():
    """Fiyatı bulunamayan bir varlık "elde tutulan sınıf" sayılmamalı —
    diğer sinyal bağlamı fonksiyonlarıyla aynı ilke (bkz.
    agents/risk_agent.py::_kullanilmayan_kapasite)."""
    holdings_data = {
        "holdings": [
            {
                "symbol": "TST",
                "asset_class": "stock",
                "weight_percent": None,
                "price_missing": True,
            }
        ]
    }

    assert _profil_uyum_disi_siniflar(holdings_data, 3) == []


def test_birden_fazla_uyumsuz_sinif_alfabetik_sirali():
    """Puan=1 (CONSERVATIVE) yalnızca NAKİT'e (seviye 1) izin verir; elde
    TAHVIL + HİSSE varsa ikisi de uyumsuzdur, sıralama deterministik olmalı."""
    holdings_data = {
        "holdings": [
            {"symbol": "A", "asset_class": "bond", "weight_percent": 50.0},
            {"symbol": "B", "asset_class": "stock", "weight_percent": 50.0},
        ]
    }

    assert _profil_uyum_disi_siniflar(holdings_data, 1) == ["bond", "stock"]


# ---------------------------------------------------------------------------
# _render — "Risk profili uyumu" bloğu
# ---------------------------------------------------------------------------


def test_render_uyumsuzluk_yoksa_blok_eklenmez():
    metin = _render({"holdings": {"holdings": []}})

    assert "Risk profili uyumu" not in metin


def test_render_uyumsuzluk_varsa_blok_eklenir_ve_turkcelesir():
    metin = _render({"holdings": {"holdings": []}, "profil_uyum_disi_siniflar": ["stock", "bond"]})

    assert "Risk profili uyumu" in metin
    # Ham enum DEĞİL, Türkçe karşılığı görünmeli.
    assert "Hisse Senedi" in metin
    assert "Borçlanma Araçları" in metin
    # Satış zorunluluğu OLMADIĞI açıkça belirtilmeli (uyarı değil, bilgilendirme).
    assert "satış zorunluluğu değildir" in metin
