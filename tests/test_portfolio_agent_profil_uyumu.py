"""Portföy Ajanı'nın profil-uygunluk bilgilendirmesi testleri.

NEDEN VAR. Bu, "risk analizi" DEĞİLDİR (o `agents/risk_agent.py`'nin işi) —
kullanıcının GÜNCEL elinde olan ama GÜNCEL anket puanının artık izin
vermediği varlıkların basit bir bildirimi (bkz. `agents/portfolio_agent.py`
modül docstring'i, `app/services/advice_eligibility.mismatched_holdings`).
`risk_agent` yalnızca kullanıcı "ne yapmalıyım" tarzı bir soru sorduğunda
çalıştığı için bu bilgi, olmasaydı, "portföyümü göster" gibi en sıradan bir
soruda hiç görünmezdi — bu dosya o boşluğu kapatan
`_profil_uyum_disi_varliklar`/`_render` mantığını test eder.

2026-08-31: kontrol SINIF düzeyinden VARLIK düzeyine çekildi. Sebebi canlıda
ölçüldü — Korumacı bir kullanıcının elindeki IOO (para piyasası fonu) için
"Borçlanma Araçları artık tavsiye kapsamında değil" deniyordu; oysa sınıfı
BOND (seviye 2) olsa da IOO'nun kendi uygunluk seviyesi 1'dir ve o kullanıcı
için uyumludur. Bu dosyadaki testler o yüzden sembol bazlı yeniden yazıldı.

Saf fonksiyon testleri gerçek bir MCP çağrısı YAPMAZ (bkz. `_fetch_risk_
survey_score`, o ayrı bir entegrasyon testinde — tests/
test_portfolio_agent_tools.py — ele alınır)."""

from agents.portfolio_agent import _profil_uyum_disi_varliklar, _render

# ---------------------------------------------------------------------------
# _profil_uyum_disi_varliklar
# ---------------------------------------------------------------------------


def test_uyumsuzluk_yok_tum_varliklar_izinli():
    """Puan=7 (AGGRESSIVE) her varlığa izin verir; hiçbir uyumsuzluk olmaz."""
    holdings_data = {
        "holdings": [{"symbol": "TST", "asset_class": "stock", "weight_percent": 100.0}]
    }

    assert _profil_uyum_disi_varliklar(holdings_data, 7) == []


def test_uyumsuzluk_var():
    """Puan=3 (BALANCED) sınıf varsayılanı 5 olan bir hisseye izin vermez."""
    holdings_data = {
        "holdings": [{"symbol": "TST", "asset_class": "stock", "weight_percent": 100.0}]
    }

    assert _profil_uyum_disi_varliklar(holdings_data, 3) == [
        {"sembol": "TST", "sinif": "stock", "seviye": 5}
    ]


def test_sinifindan_AYRILAN_varlik_dogru_degerlendirilir():
    """Asıl düzeltmenin kilidi. IOO bir para piyasası fonu: sınıfı BOND
    (seviye 2) ama kendi uygunluk seviyesi 1.

    Puanı 1 olan Korumacı kullanıcı için SINIF karşılaştırmasi (2 > 1)
    "uyumsuz" derdi — canlıda tam olarak bu yanlış bildirim yapılıyordu.
    Varlık düzeyi karşılaştırması (1 <= 1) uyumlu der; doğru olan budur.
    """
    holdings_data = {"holdings": [{"symbol": "IOO", "asset_class": "bond", "weight_percent": 37.6}]}

    assert _profil_uyum_disi_varliklar(holdings_data, 1) == []


def test_sinifindan_YUKARI_ayrilan_varlik_yakalanir():
    """Ters yön: BHE serbest fonu STOCK sınıfındadır (5) ama kendi seviyesi
    7'dir. Puanı 5 olan kullanıcı için sınıf "uyumlu" derdi, varlık düzeyi
    uyumsuz der."""
    holdings_data = {
        "holdings": [{"symbol": "BHE", "asset_class": "stock", "weight_percent": 10.0}]
    }

    assert _profil_uyum_disi_varliklar(holdings_data, 5) == [
        {"sembol": "BHE", "sinif": "stock", "seviye": 7}
    ]


def test_anket_bossa_kontrol_atlanir():
    """`risk_survey_score=None` (anket hiç doldurulmamış) — uydurma yok,
    kontrol tamamen atlanır."""
    holdings_data = {
        "holdings": [{"symbol": "TST", "asset_class": "stock", "weight_percent": 100.0}]
    }

    assert _profil_uyum_disi_varliklar(holdings_data, None) == []


def test_fiyati_eksik_varlik_elde_sayilmaz():
    """Fiyatı bulunamayan bir varlık "elde tutulan" sayılmamalı — diğer
    sinyal bağlamı fonksiyonlarıyla aynı ilke (bkz.
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

    assert _profil_uyum_disi_varliklar(holdings_data, 3) == []


def test_birden_fazla_uyumsuz_varlik_sembole_gore_sirali():
    """Puan=1 yalnızca seviye 1'e izin verir; sıralama deterministik olmalı
    ki yanıt turdan tura değişmesin."""
    holdings_data = {
        "holdings": [
            {"symbol": "ZZZ", "asset_class": "stock", "weight_percent": 50.0},
            {"symbol": "AAA", "asset_class": "currency", "weight_percent": 50.0},
        ]
    }

    assert [k["sembol"] for k in _profil_uyum_disi_varliklar(holdings_data, 1)] == [
        "AAA",
        "ZZZ",
    ]


def test_taninmayan_sinif_sessizce_atlanir():
    """Beklenmeyen bir sınıf değeri kontrolü çökertmemeli; yalnızca o varlık
    atlanır, diğerleri değerlendirilmeye devam eder."""
    holdings_data = {
        "holdings": [
            {"symbol": "GARIP", "asset_class": "boyle_bir_sinif_yok", "weight_percent": 50.0},
            {"symbol": "TST", "asset_class": "stock", "weight_percent": 50.0},
        ]
    }

    assert [k["sembol"] for k in _profil_uyum_disi_varliklar(holdings_data, 3)] == ["TST"]


# ---------------------------------------------------------------------------
# _render — "Risk profili uyumu" bloğu
# ---------------------------------------------------------------------------


def test_render_uyumsuzluk_yoksa_blok_eklenmez():
    metin = _render({"holdings": {"holdings": []}})

    assert "Risk profili uyumu" not in metin


def test_render_uyumsuzluk_varsa_sembol_seviye_ve_puan_gorunur():
    metin = _render(
        {
            "holdings": {"holdings": []},
            "profil_uyum_disi_varliklar": [
                {"sembol": "BHE", "sinif": "stock", "seviye": 7},
            ],
            "anket_puani": 5,
        }
    )

    assert "Risk profili uyumu" in metin
    assert "BHE" in metin
    # Ham enum DEGIL, Turkce karsiligi gorunmeli.
    assert "Hisse Senedi" in metin
    # Gerekce somut olmali: varligin kendi seviyesi + kullanicinin puani.
    assert "uygunluk seviyesi 7" in metin
    assert "Anket puanınız 5" in metin
    # Satis zorunlulugu OLMADIGI acikca belirtilmeli (uyari degil, bilgilendirme).
    assert "satış zorunluluğu değildir" in metin


def test_render_puan_yoksa_cumle_bozulmaz():
    """`anket_puani` bir sebeple taşınmadıysa blok yine de anlamlı kalmalı."""
    metin = _render(
        {
            "holdings": {"holdings": []},
            "profil_uyum_disi_varliklar": [
                {"sembol": "BHE", "sinif": "stock", "seviye": 7},
            ],
        }
    )

    assert "BHE" in metin
    assert "Anket puanınız" not in metin
    assert "satış zorunluluğu değildir" in metin
