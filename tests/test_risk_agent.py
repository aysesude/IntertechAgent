"""Risk/Strateji Ajanı'nın LLM'e gitmeyen kısımları: senaryo tetikleme kararı
ve değerlendirmenin küçültülmesi."""

from agents.risk_agent import _compact, _wants_scenarios


def test_senaryo_yalnizca_aksiyon_sorularinda_istenir():
    """Senaryo üretimi ek hesap maliyeti; yalnızca kullanıcı gerçekten "ne
    yapmalıyım" diye sorduğunda açılır."""
    assert _wants_scenarios("portföyümü nasıl dengelerim") is True
    assert _wants_scenarios("riskimi azaltmak istiyorum") is True
    assert _wants_scenarios("bir öneri verir misin") is True
    assert _wants_scenarios("ne yapmalıyım") is True
    # Aksansiz yazim da yakalanmali (Turkce klavyesi olmayan kullanici).
    assert _wants_scenarios("riskimi azaltmak icin oneri") is True

    assert _wants_scenarios("riskim ne durumda") is False
    assert _wants_scenarios("volatilitem kaç") is False


def test_compact_hesaplanamayan_alanlari_silmez():
    """Uydurmama ilkesi (CLAUDE.md §4): risk hesaplanamadığında LLM bunu
    görüp "hesaplanamadı" demeli. Alan silinirse model boşluğu doldurmaya
    açık kalır."""
    assessment = {
        "as_of": "2026-08-20",
        "risk_profile": "growth",
        "risk_level": None,
        "is_within_profile": None,
        "total_value": 0.0,
        "metrics": {
            "annualized_volatility_percent": None,
            "value_at_risk_try": None,
            "sharpe_ratio": None,
            "holdings_count": 0,
        },
        "causes": None,
        "scenarios": [],
        "warnings": ["Portföyünüzde varlık bulunmuyor."],
    }

    compact = _compact(assessment)

    assert compact["risk_seviyesi"] is None
    assert compact["yillik_volatilite_yuzde"] is None
    assert compact["sharpe_orani"] is None
    assert compact["uyarilar"] == ["Portföyünüzde varlık bulunmuyor."]
    # Bos alanlar icin anahtar hic eklenmez (LLM'i mesgul etmesin).
    assert "riskin_nedenleri" not in compact
    assert "yeniden_dengeleme_secenekleri" not in compact


def test_compact_tetiklenen_nedenleri_turkcelestirir():
    assessment = {
        "metrics": {},
        "causes": {
            "concentration": {"triggered": True},
            "high_volatility_asset": {"triggered": False},
            "correlation": {"triggered": True},
        },
        "scenarios": [
            {
                "label": "Dengeli Düzeltme",
                "volatility_before_percent": 34.0,
                "volatility_after_percent": 28.0,
                "turnover_percent": 12.0,
                # LLM'e gitmemesi gereken ayrintili kirilim:
                "asset_weights": [{"asset_symbol": "TST"}],
            }
        ],
    }

    compact = _compact(assessment)

    assert compact["riskin_nedenleri"] == ["Yoğunlaşma", "Yüksek korelasyon"]
    assert compact["yeniden_dengeleme_secenekleri"] == [
        {
            "ad": "Dengeli Düzeltme",
            "volatilite_once_yuzde": 34.0,
            "volatilite_sonra_yuzde": 28.0,
            "islem_hacmi_yuzde": 12.0,
        }
    ]


def test_profil_sinirlari_karsilastirma_icin_tasiniyor():
    """ "Çok fazla hisse mi var" sorusu ancak bir ÖLÇÜTLE cevaplanabilir.

    Ölçüldü: ajan "%27,51" deyip bırakıyor, Korumacı profilin %25 üst sınırına
    hiç değinmiyordu — soru cevapsız kalıyordu. Eşikler burada hesaplanmıyor,
    config'deki tek tanımdan okunuyor.
    """
    compact = _compact({"risk_profile": "conservative", "metrics": {}})

    assert compact["profil_hedef_volatilite_bandi_yuzde"] == [0.0, 10.0]
    assert compact["profil_kategori_ust_sinirlari_yuzde"]["stock"] == 25.0
    # Tahvil/nakit Korumacı profilde üst sınırsız (alt sınır var, üst yok).
    assert compact["profil_kategori_ust_sinirlari_yuzde"]["bond"] == 100.0


def test_taninmayan_profil_cokmez_sinir_eklemez():
    """Profil değeri beklenmedikse uydurulmuş bir sınır gösterilmez."""
    compact = _compact({"risk_profile": "yok_boyle_bir_profil", "metrics": {}})

    assert "profil_kategori_ust_sinirlari_yuzde" not in compact
    assert "profil_hedef_volatilite_bandi_yuzde" not in compact


def test_butun_senaryolar_tasiniyor():
    """Motor üçe kadar senaryo üretiyor; hiçbiri düşürülmemeli.

    Canlıda cevapta tek seçenek görünmüştü — prompt "yalnızca adını aktar"
    ifadesini "yalnızca birini aktar" diye okumuş olabilir. Taşıma katmanının
    hepsini verdiği burada kilitleniyor.
    """
    scenarios = [
        {
            "label": f"Senaryo {i}",
            "volatility_before_percent": 12.7,
            "volatility_after_percent": 9.0 + i,
            "turnover_percent": 5.0 * i,
        }
        for i in range(1, 4)
    ]
    compact = _compact({"risk_profile": "balanced", "metrics": {}, "scenarios": scenarios})

    secenekler = compact["yeniden_dengeleme_secenekleri"]
    assert len(secenekler) == 3
    assert [s["ad"] for s in secenekler] == ["Senaryo 1", "Senaryo 2", "Senaryo 3"]
    # Hangi varlığın alınıp satılacağı LLM'e HİÇ gitmemeli (tavsiye yasağı).
    assert all("asset_weights" not in s and "varliklar" not in s for s in secenekler)
