"""Risk/Strateji Ajanı'nın LLM'e gitmeyen kısımları: senaryo tetikleme kararı
ve değerlendirmenin küçültülmesi.

2026-08-22 eki: sinyal tabanlı risk değerlendirmesinin (bkz. modül
docstring'i, agents/prompts/risk_signals.md) LLM'e GİTMEYEN yardımcıları —
dummy anket puanı eşlemesi, LLM çıktısının JSON'a ayrıştırılması, ham tool
verisinin LLM bağlamına dönüştürülmesi. `_assess_signals`'ın kendisi gerçek
bir LLM çağrısı yaptığı için burada test edilmiyor; ajanın diğer LLM'li
kısımlarında olduğu gibi (`_summarize`) bu proje deterministik pytest yerine
manuel/entegrasyon doğrulaması kullanıyor."""

import json

import pytest

from agents.risk_agent import (
    _SIGNAL_PROMPT_TEMPLATE,
    _build_signal_context,
    _compact,
    _dummy_survey_score,
    _extract_json_object,
    _render_signal_prompt,
    _wants_scenarios,
)
from app.core.config import RiskProfile


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


def _konum(profil: str, vol, within):
    return _compact(
        {
            "risk_profile": profil,
            "is_within_profile": within,
            "metrics": {"annualized_volatility_percent": vol},
        }
    ).get("profil_konumu")


def test_profil_altinda_kalmak_ayri_bir_durum():
    """Bandın ALTINDA kalmak "içinde" sayılmamalı.

    risk_service yalnızca üst sınırı kontrol ediyor
    (`is_within_profile = volatility <= band_upper`), dolayısıyla Agresif
    profilli %3,5 volatiliteli bir kullanıcıya "profilinizin içindesiniz"
    deniyordu. Ölçüldü: 50 kullanıcının 32'si bu durumda ve sisteme göre
    hepsinde "her şey yolunda".
    """
    # Agresif bandı %30-40; %3,5 çok altında.
    assert _konum("aggressive", 3.5, True) == "bandin_altinda"
    # Dengeli bandı %10-20.
    assert _konum("balanced", 5.0, True) == "bandin_altinda"


def test_ust_sinir_karari_servisten_alinir():
    """Üst sınır kararı yeniden hesaplanmaz; iki katman çelişemez."""
    assert _konum("conservative", 12.6, False) == "bandin_ustunde"
    # Servis "içinde" diyorsa ajan bunu bozmaz.
    assert _konum("aggressive", 35.0, True) == "band_icinde"


def test_korumaci_profilde_bandin_altinda_olamaz():
    """Korumacı bandının alt sınırı %0 — sıfırdan az risk yok."""
    assert _konum("conservative", 0.5, True) == "band_icinde"


def test_risk_hesaplanamadiysa_konum_uretilmez():
    """Volatilite yoksa konum uydurulmaz (CLAUDE.md §4)."""
    assert _konum("balanced", None, None) is None
    assert _konum("balanced", None, True) is None


def test_celisen_iki_alan_birlikte_gonderilmez():
    """`profil_bandinda_mi` ile `profil_konumu` aynı anda bulunmamalı.

    `is_within_profile` yalnızca ÜST sınırı kontrol ediyor, dolayısıyla bandın
    altındaki portföyde `true` olur ve `profil_konumu="bandin_altinda"` ile
    yüzeyde çelişir. Canlıda model bu çelişkiyi fark edip açıklamaya çalıştı ve
    iç alan adlarını kullanıcıya yazdı:

        "profil_bandinda_mi alanında 'evet' bilgisi yer alsa da profil_konumu
         alanı portföyün beklenen aralığın altında olduğunu gösteriyor."

    Konum alanı üç durumu da ayırdığı için ikili alanın yerini alır.
    """
    for profil, vol, within in [
        ("aggressive", 3.29, True),
        ("conservative", 15.48, False),
        ("balanced", 15.0, True),
    ]:
        compact = _compact(
            {
                "risk_profile": profil,
                "is_within_profile": within,
                "metrics": {"annualized_volatility_percent": vol},
            }
        )
        assert "profil_konumu" in compact
        assert "profil_bandinda_mi" not in compact, f"{profil}: iki alan birlikte gitti"


def test_konum_hesaplanamazsa_ikili_alan_korunur():
    """Konum üretilemiyorsa bilgi tamamen kaybolmamalı."""
    # Tanınmayan profil: band bilinmiyor, konum hesaplanamaz.
    compact = _compact(
        {
            "risk_profile": "yok_boyle_bir_profil",
            "is_within_profile": True,
            "metrics": {"annualized_volatility_percent": 12.0},
        }
    )
    assert compact["profil_bandinda_mi"] is True
    assert "profil_konumu" not in compact


def test_prompt_alan_adi_yazmayi_yasakliyor():
    """Sızıntının ikinci savunması prompt'ta olmalı.

    Alan adları prompt'ta geçmek zorunda (modele veriyi nerede bulacağını
    söylüyorlar), bu yüzden "yazma" kuralı açıkça bulunmalı.
    """
    from agents.risk_agent import _PROMPT_TEMPLATE

    assert "JSON ALAN ADLARINI ASLA YAZMA" in _PROMPT_TEMPLATE


def test_dummy_anket_puani_profile_gore_esleniyor():
    """Gerçek anket gelene kadarki GEÇİCİ eşleme (bkz. modül docstring'i).

    Puanlar bilinçli olarak advice_eligibility.ASSET_CLASS_ADVICE_RISK_LEVEL
    kırılım noktalarına denk düşecek şekilde seçildi; tablo 26 Ağustos
    2026'da yeniden kalibre edilince eşlemenin kendisi değişmedi ama artık
    dört profil dört FARKLI izin kümesi üretiyor (önce BALANCED ve GROWTH
    aynı sonucu veriyordu).
    """
    assert _dummy_survey_score(RiskProfile.CONSERVATIVE) == 2
    assert _dummy_survey_score(RiskProfile.BALANCED) == 4
    assert _dummy_survey_score(RiskProfile.GROWTH) == 5
    assert _dummy_survey_score(RiskProfile.AGGRESSIVE) == 7


def test_dummy_anket_puani_profil_yoksa_none():
    """Profil tanınmıyorsa ya da hiç yoksa puan uydurulmaz."""
    assert _dummy_survey_score(None) is None


def test_json_ciktisi_kod_bloguyla_gelirse_ayiklanir():
    """Prompt "yalnızca JSON" istiyor ama modeller sık sık ``` bloğuna sarar
    (bkz. _extract_json_object docstring'i); bu tolere edilmeli."""
    duz = '{"risk_level": "az_riskli"}'
    ucgen_json_etiketli = '```json\n{"risk_level": "az_riskli"}\n```'
    ucgen_etiketsiz = '```\n{"risk_level": "az_riskli"}\n```'

    for metin in (duz, ucgen_json_etiketli, ucgen_etiketsiz):
        assert _extract_json_object(metin) == {"risk_level": "az_riskli"}


def test_json_ciktisi_bozuksa_hata_yukselir():
    """Onarım denenmez (bkz. fonksiyon docstring'i): bozuk JSON çağıran
    tarafa görünür bir hata olarak gitmeli, sessizce doldurulmamalı."""
    with pytest.raises(json.JSONDecodeError):
        _extract_json_object("bu JSON degil")


def test_sinyal_baglami_fiyati_eksik_varligi_disliyor():
    """Fiyatı bulunamayan varlık ağırlık hesabına girmediği gibi (bkz.
    get_holdings sözleşmesi) sinyal bağlamına da girmemeli."""
    holdings_data = {
        "holdings": [
            {"symbol": "TST", "asset_class": "stock", "weight_percent": 60.0},
            {
                "symbol": "XYZ",
                "asset_class": "bond",
                "weight_percent": None,
                "price_missing": True,
            },
        ]
    }
    news_data = {"assets": [], "assets_without_documents": ["TST"], "confidence": "low"}

    context = _build_signal_context(holdings_data, news_data, None, None)

    assert context["varliklar"] == [{"sembol": "TST", "sinif": "stock", "agirlik_yuzde": 60.0}]
    assert context["haber_kapsami_olmayan_varliklar"] == ["TST"]
    assert context["haber_guven_duzeyi"] == "low"


def test_sinyal_baglami_haberleri_sembole_gore_grupluyor():
    """Her varlığın haber/bilanço/yorum parçaları kendi sembolü altında,
    beklenen alan adlarıyla (tur/baslik/tarih/kaynak/icerik) toplanmalı."""
    holdings_data = {
        "holdings": [{"symbol": "TST", "asset_class": "stock", "weight_percent": 100.0}]
    }
    news_data = {
        "assets": [
            {
                "symbol": "TST",
                "documents": [
                    {
                        "tur": "haber",
                        "baslik": "Şirket X büyüme rakamlarını açıkladı",
                        "tarih": "2026-08-20",
                        "kaynak": "Örnek Kaynak",
                        "content": "İçerik metni.",
                    }
                ],
            }
        ],
        "assets_without_documents": [],
        "confidence": "normal",
    }

    context = _build_signal_context(holdings_data, news_data, None, None)

    assert context["haberler"]["TST"] == [
        {
            "tur": "haber",
            "baslik": "Şirket X büyüme rakamlarını açıkladı",
            "tarih": "2026-08-20",
            "kaynak": "Örnek Kaynak",
            "icerik": "İçerik metni.",
        }
    ]


def test_sinyal_baglami_dummy_puan_yoksa_alanlar_eklenmez():
    """Profil tanınmıyorsa (dummy puan üretilemiyorsa) anket/izin alanları
    bağlama hiç eklenmemeli — uydurulmuş bir puan görünmemeli."""
    context = _build_signal_context({"holdings": []}, {"assets": []}, None, None)

    assert "survey_puani_dummy" not in context
    assert "survey_puani_dummy_uyarisi" not in context
    assert "bu_puanla_izinli_siniflar" not in context


def test_sinyal_baglami_dummy_puan_uyarisiyla_ve_izinli_siniflarla_gelir():
    """Dummy puan varsa hem açık bir uyarı hem de o puanla izinli varlık
    sınıfları bağlama eklenmeli (LLM'in "profil_sapmasi" sinyalini
    değerlendirebilmesi için)."""
    context = _build_signal_context({"holdings": []}, {"assets": []}, RiskProfile.CONSERVATIVE, 2)

    assert context["survey_puani_dummy"] == 2
    assert "GERÇEK bir anket sonucu değildir" in context["survey_puani_dummy_uyarisi"]
    # Korumacı dummy puanı (2): nakit (1) ve tahvil (2) sınıflarını geçer.
    # Eski tabloda tahvil 3'tü ve bu puan YALNIZCA nakit açıyordu — yani
    # muhafazakâr kullanıcıya önerilebilecek tek şey, satın alınamayan
    # serbest bakiyeydi. Yeniden kalibrasyon bunu da düzeltti.
    assert context["bu_puanla_izinli_siniflar"] == ["bond", "cash"]


def test_sinyal_prompt_semadaki_literal_suslu_parantezlerle_kirilmiyor():
    """REGRESYON: risk_signals.md'nin çıktı biçimi bölümünde literal JSON
    örneği (`{`/`}` karakterleri) var — bunlarla dolu bir şablonu `.format()`
    ile doldurmaya çalışmak `ValueError: unmatched '{'` ile patlar (Python
    `.format()` her `{`/`}`'i bir yer tutucu sanır). `_render_signal_prompt`
    bu yüzden `.format()` DEĞİL `.replace()` kullanıyor; bu test hem şablonun
    gerçekten literal süslü parantez içerdiğini (regresyonun hâlâ mümkün
    olduğunu) hem de `_render_signal_prompt`'un bunlara rağmen çökmediğini
    doğruluyor."""
    # Şablon değişmişse bu varsayım da geçersiz kalabilir — önce onu kontrol et.
    assert '"risk_level"' in _SIGNAL_PROMPT_TEMPLATE
    assert _SIGNAL_PROMPT_TEMPLATE.count("{context_json}") == 1

    rendered = _render_signal_prompt({"varliklar": [{"sembol": "TST", "agirlik_yuzde": 60.0}]})

    assert "{context_json}" not in rendered
    assert '"sembol": "TST"' in rendered
    # Şemadaki literal parantezler dokunulmadan kalmalı (kaçırılmamalı/silinmemeli).
    assert '"risk_level": "az_riskli"' in rendered
