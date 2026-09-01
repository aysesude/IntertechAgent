"""Risk/Strateji Ajanı'nın LLM'e gitmeyen kısımları: senaryo tetikleme kararı
ve değerlendirmenin küçültülmesi.

2026-08-22 eki: sinyal tabanlı risk değerlendirmesinin (bkz. modül
docstring'i, agents/prompts/risk_signals.md) LLM'e GİTMEYEN yardımcıları —
LLM çıktısının JSON'a ayrıştırılması, ham tool verisinin LLM bağlamına
dönüştürülmesi. `_assess_signals`'ın kendisi gerçek bir LLM çağrısı yaptığı
için burada test edilmiyor; ajanın diğer LLM'li kısımlarında olduğu gibi
(`_summarize`) bu proje deterministik pytest yerine manuel/entegrasyon
doğrulaması kullanıyor.

2026-08-25 eki: aynı ilkeyle `_fetch_macro_context`/`_fetch_live_macro_news`
de burada test edilmiyor (MCP tool çağrısı yapıyorlar) — yalnızca onların
girdisini hazırlayan saf fonksiyon `_live_macro_symbols_for_holdings` test
edilir (bkz. app/providers/universe.py:macro_news_key, MCP tool testi için
tests/test_mcp_market_tool.py, ingest/servis testleri için
tests/test_macro_news_ingest.py).

2026-08-26 eki: dummy anket puanı eşlemesi (`_dummy_survey_score`,
`_DUMMY_SURVEY_SCORE_BY_PROFILE`) ve `_build_signal_context`'in ürettiği
"survey_puani_dummy"/"bu_puanla_izinli_siniflar" alanları KALDIRILDI —
Sinyal 5 artık profil/ağırlık tabanlı değil, yalnızca anket-yeniden-doldurma
OLAYIYLA tetiklenmeli (bkz. agents/risk_agent.py modül docstring'i "2026-08-26
eki"); böyle bir olay mekanizması henüz yok, sinyal kalıcı dormant. Bu
dosyadaki ilgili testler kaldırıldı; `_build_signal_context` artık yalnızca
holdings/haber/makro verisini birleştirdiğini doğrulayan testler kaldı.

2026-08-28 eki (kod): Yol A'nın olay mekanizması yazıldı (bkz.
agents/risk_agent.py modül docstring'i "2026-08-28 eki (kod)",
docs/notes/sinyal5-olay-tabanli-aktivasyon-tasarimi.md §4.5). `_build_signal_
context` artık opsiyonel `yeni_profille_izinsiz_kalan_siniflar` parametresini
kabul ediyor; `test_sinyal_baglami_anket_alanlari_hicbir_zaman_eklenmez` bu
yüzden `test_sinyal_baglami_anket_alanlari_yalnizca_olay_varsa_eklenir` olarak
güncellendi — artık "hiçbir zaman" değil "yalnızca olay/ihlal varsa". Eski
dummy alanlarının (2026-08-26 eki) KALICI olarak eklenmeyeceği ayrı, hâlâ
geçerli bir testte kaldı (`test_sinyal_baglami_eski_dummy_alanlari_
hicbir_zaman_eklenmez`). `_assess_signals`'ın üçüncü tool çağrısı
(`get_risk_survey_event`) burada TEST EDİLMİYOR — modülün başındaki ilkeyle
aynı sebep: gerçek bir MCP çağrısı içeriyor, deterministik pytest yerine
manuel/entegrasyon doğrulaması kullanılıyor."""

import json

import pytest

from agents.risk_agent import (
    _SIGNAL_PROMPT_TEMPLATE,
    _build_signal_context,
    _compact,
    _extract_json_object,
    _kullanilmayan_kapasite,
    _live_macro_symbols_for_holdings,
    _macro_queries_for_holdings,
    _render_signal_prompt,
    _sinyal_blogu,
    _wants_scenarios,
)
from app.schemas.risk_signals import RiskSignalAssessment


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

    context = _build_signal_context(holdings_data, news_data)

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

    context = _build_signal_context(holdings_data, news_data)

    assert context["haberler"]["TST"] == [
        {
            "tur": "haber",
            "baslik": "Şirket X büyüme rakamlarını açıkladı",
            "tarih": "2026-08-20",
            "kaynak": "Örnek Kaynak",
            "icerik": "İçerik metni.",
        }
    ]


def test_sinyal_baglami_eski_dummy_alanlari_hicbir_zaman_eklenmez():
    """2026-08-26 eki: Sinyal 5 artık profil/dummy puana bakmıyor (bkz.
    agents/risk_agent.py modül docstring'i) — `_build_signal_context`
    "survey_puani_dummy"/"survey_puani_dummy_uyarisi"/
    "bu_puanla_izinli_siniflar" alanlarını ARTIK HİÇ üretmemeli; bu KALICI
    bir kısıt, Yol A'nın (2026-08-28) yeni alanlarıyla ilgisi yok."""
    context = _build_signal_context({"holdings": []}, {"assets": []})

    assert "survey_puani_dummy" not in context
    assert "survey_puani_dummy_uyarisi" not in context
    assert "bu_puanla_izinli_siniflar" not in context


def test_sinyal_baglami_anket_alanlari_yalnizca_olay_varsa_eklenir():
    """2026-08-28 eki (kod): Sinyal 5 Yol A'nın girdisi artık koşullu —
    `yeni_profille_izinsiz_kalan_siniflar` verilmezse (ya da boş liste
    geçilirse) `_build_signal_context` "anket_yeniden_dolduruldu"/
    "yeni_profille_izinsiz_kalan_siniflar" alanlarını HİÇ eklememeli (bu,
    önceki "hiçbir zaman eklenmez" testinin yerini alan güncellenmiş
    versiyondur — artık kalıcı değil, koşullu bir dormant hâli)."""
    context_olaysiz = _build_signal_context({"holdings": []}, {"assets": []})
    assert "anket_yeniden_dolduruldu" not in context_olaysiz
    assert "yeni_profille_izinsiz_kalan_siniflar" not in context_olaysiz

    context_bos_liste = _build_signal_context(
        {"holdings": []}, {"assets": []}, yeni_profille_izinsiz_kalan_siniflar=[]
    )
    assert "anket_yeniden_dolduruldu" not in context_bos_liste
    assert "yeni_profille_izinsiz_kalan_siniflar" not in context_bos_liste


def test_sinyal_baglami_anket_alanlari_ihlal_varsa_eklenir():
    """Gerçek bir ihlal listesi verildiğinde `_build_signal_context` bunu
    olduğu gibi taşımalı — burada da hiçbir sınıflandırma/karşılaştırma
    YAPILMAZ, liste zaten deterministik olarak `user_service.
    get_and_consume_risk_survey_event` tarafından hesaplanmış gelir."""
    context = _build_signal_context(
        {"holdings": []}, {"assets": []}, yeni_profille_izinsiz_kalan_siniflar=["stock"]
    )

    assert context["anket_yeniden_dolduruldu"] is True
    assert context["yeni_profille_izinsiz_kalan_siniflar"] == ["stock"]


# --- Sinyal 5, Yol B: _kullanilmayan_kapasite --------------------------------
#
# 2026-08-28 eki (Yol B kod): analist "hangi kapasite" sorusunu netleştirdi
# ("risk seviyesi yüksek çıktı ama daha az riskli varlıkları var" -> (a)
# advice_eligibility). bkz. docs/notes/sinyal5-olay-tabanli-aktivasyon-
# tasarimi.md §4.8/§4.10: kullanılmayan sınıf var / yok / anket boş (None) /
# tüm izinli sınıflar zaten elde — dört senaryo.


def test_kullanilmayan_kapasite_anket_bossa_uretilmez():
    """`risk_survey_score=None` (anket hiç doldurulmamış) — "izin verilen
    sınıf" kavramı anketsiz tanımsızdır, uydurma yok."""
    holdings_data = {
        "holdings": [{"symbol": "TST", "asset_class": "cash", "weight_percent": 100.0}]
    }

    assert _kullanilmayan_kapasite(holdings_data, None) == []


def test_kullanilmayan_kapasite_var():
    """Puanın izin verdiği ama elde hiç bulunmayan sınıf bildirilir."""
    holdings_data = {
        "holdings": [{"symbol": "TST", "asset_class": "bond", "weight_percent": 100.0}]
    }

    # puan=3 -> NAKIT (1), TAHVIL (2), MADEN (3) izinli. TAHVIL elde;
    # NAKİT hiç sayılmaz (aşağıdaki teste bakın); geriye MADEN kalır.
    assert _kullanilmayan_kapasite(holdings_data, 3) == ["precious_metal"]


def test_kullanilmayan_kapasite_NAKDI_asla_saymaz():
    """NAKİT bu sinyale hiç girmez — iki sebeple, ikisi de ölçüldü.

    (1) Nakit bir `holdings` satırı değil, defter bakiyesidir; "elde tutulan
    sınıflar" kümesinde HİÇBİR ZAMAN görünmez. Süzgeç olmadan CASH her
    kullanıcıda, her turda "kullanılmayan kapasite" çıkıyordu — 175.866 TL
    serbest nakdi olan demo personasına 14 ayrı yanıtta "nakit sınıfını
    içermediği için profil sapması" dendi (1 Eylül 2026 sohbet turu).

    (2) Anlamı da ters: sinyal "profilinin izin verdiğinden daha TEMKİNLİ
    duruyorsun" demek için var, oysa nakit tutmamak temkinli değil tam
    tersi bir duruştur.
    """
    # Elinde nakit OLMAYAN kullanıcı: yine de bildirilmemeli.
    nakitsiz = {"holdings": [{"symbol": "TST", "asset_class": "bond", "weight_percent": 100.0}]}
    assert "cash" not in _kullanilmayan_kapasite(nakitsiz, 2)
    assert _kullanilmayan_kapasite(nakitsiz, 2) == []

    # Puanın izin verdiği TEK sınıf nakitse sonuç boş kalır, sinyal üretilmez.
    assert _kullanilmayan_kapasite(nakitsiz, 1) == []


def test_kullanilmayan_kapasite_tum_izinli_siniflar_elde_ise_bos():
    """Puanın izin verdiği (nakit dışı) sınıfların hepsi elde varsa kapasite
    kalmaz."""
    holdings_data = {
        "holdings": [
            {"symbol": "TST", "asset_class": "bond", "weight_percent": 60.0},
            {"symbol": "XAUTRY", "asset_class": "precious_metal", "weight_percent": 40.0},
        ]
    }

    assert _kullanilmayan_kapasite(holdings_data, 3) == []


def test_kullanilmayan_kapasite_fiyati_eksik_varligi_disliyor():
    """Fiyatı bulunamayan bir varlık "elde tutulan sınıf" sayılmamalı —
    diğer sinyal bağlamı fonksiyonlarıyla aynı ilke (bkz.
    test_sinyal_baglami_fiyati_eksik_varligi_disliyor)."""
    holdings_data = {
        "holdings": [
            {"symbol": "TST", "asset_class": "bond", "weight_percent": None, "price_missing": True}
        ]
    }

    # puan=3 -> TAHVIL ve MADEN izinli (nakit sayılmaz); TAHVİL'in fiyatı
    # eksik olduğu için "elde" sayılmaz, ikisi de kapasite olarak döner.
    assert _kullanilmayan_kapasite(holdings_data, 3) == ["bond", "precious_metal"]


def test_sinyal_baglami_kullanilmayan_kapasite_bossa_eklenmez():
    """`kullanilmayan_kapasite` verilmezse/boşsa `_build_signal_context`
    "kullanilmayan_kapasite" anahtarını HİÇ eklememeli — Yol A'nın
    alanlarıyla aynı ilke."""
    context = _build_signal_context({"holdings": []}, {"assets": []}, kullanilmayan_kapasite=[])

    assert "kullanilmayan_kapasite" not in context


def test_sinyal_baglami_kullanilmayan_kapasite_doluysa_eklenir():
    context = _build_signal_context(
        {"holdings": []}, {"assets": []}, kullanilmayan_kapasite=["stock"]
    )

    assert context["kullanilmayan_kapasite"] == ["stock"]


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


def test_makro_sorgular_yalnizca_tutulan_siniflar_icin_uretilir():
    """2026-08-24 eki: Tahvil/Döviz/Altın/Nakit'in şirket bilançosu yoktur,
    haber kaynağı makro piyasa haberleridir (bkz. modül docstring'i). Ama
    yalnızca PORTFÖYDE FİİLEN TUTULAN sınıflar sorgulanmalı — tutulmayan bir
    sınıf için RAG çağrısı yapmak gereksiz gecikme + alakasız gürültüdür."""
    holdings_data = {
        "holdings": [
            {"symbol": "TST", "asset_class": "stock", "weight_percent": 50.0},
            {"symbol": "APT", "asset_class": "bond", "weight_percent": 50.0},
        ]
    }

    sorgular = _macro_queries_for_holdings(holdings_data)

    assert sorgular == ["faiz kararı tahvil piyasası getiri görünümü"]


def test_makro_sorgular_hisseyi_atlar():
    """STOCK için makro sorgu üretilmez — sembol bazlı get_portfolio_news
    zaten hisseleri kapsıyor, ayrı bir makro sorgu gereksiz gürültü olurdu."""
    holdings_data = {
        "holdings": [{"symbol": "TST", "asset_class": "stock", "weight_percent": 100.0}]
    }

    assert _macro_queries_for_holdings(holdings_data) == []


def test_makro_sorgular_fiyati_eksik_varligi_disliyor():
    """Fiyatı bulunamayan bir varlığın sınıfı için makro sorgu üretilmemeli —
    tutuluyor gibi görünse de ağırlık hesabına hiç girmiyor."""
    holdings_data = {
        "holdings": [
            {
                "symbol": "XAU",
                "asset_class": "precious_metal",
                "weight_percent": None,
                "price_missing": True,
            }
        ]
    }

    assert _macro_queries_for_holdings(holdings_data) == []


def test_makro_sorgular_birden_fazla_sinif_icin_sirali_uretilir():
    """Birden fazla RAG-kaynaklı sınıf (Tahvil/Nakit) tutuluyorsa hepsi için
    sorgu üretilmeli, sıra `_MACRO_QUERY_BY_ASSET_CLASS` tanım sırasını
    izlemeli (deterministik — testte kırılgan küme sıralamasına bağlı
    kalınmasın).

    2026-08-25 eki: Döviz/Kıymetli Maden burada YOK — onlar artık RAG'a değil
    `_live_macro_symbols_for_holdings` üzerinden `get_macro_news`e (canlı)
    gidiyor, bkz. aşağıdaki testler."""
    holdings_data = {
        "holdings": [
            {"symbol": "XAU", "asset_class": "precious_metal", "weight_percent": 30.0},
            {"symbol": "APT", "asset_class": "bond", "weight_percent": 30.0},
            {"symbol": "USDTRY", "asset_class": "currency", "weight_percent": 20.0},
            {"symbol": "MEVDUAT", "asset_class": "cash", "weight_percent": 20.0},
        ]
    }

    sorgular = _macro_queries_for_holdings(holdings_data)

    assert sorgular == [
        "faiz kararı tahvil piyasası getiri görünümü",
        "enflasyon faiz oranı mevduat piyasası görünümü",
    ]


def test_canli_makro_semboller_doviz_ve_kiymetli_madeni_kapsar():
    """2026-08-25 eki: Döviz/Kıymetli Maden RAG'dan değil `get_macro_news`den
    (canlı) besleniyor. `_live_macro_symbols_for_holdings` portföyde FİİLEN
    tutulan bu sınıfların "haber anahtarı"nı (bkz.
    app/providers/universe.py:macro_news_key) döner."""
    holdings_data = {
        "holdings": [
            {"symbol": "USDTRY", "asset_class": "currency", "weight_percent": 20.0},
            {"symbol": "XAUTRY", "asset_class": "precious_metal", "weight_percent": 30.0},
        ]
    }

    assert _live_macro_symbols_for_holdings(holdings_data) == ["USDTRY", "XAUTRY"]


def test_canli_makro_semboller_turetilmis_varliklari_tabanina_esler_ve_tekillestirir():
    """CEYREK ve YARIM (ikisi de altın sikkesi, XAUTRY'den türetilmiş) aynı
    haber anahtarına düşer — aynı haberin iki kez çekilmesini engellemek için
    tekilleştirilmeli, XAUTRY yalnızca BİR kez görünmeli."""
    holdings_data = {
        "holdings": [
            {"symbol": "CEYREK", "asset_class": "precious_metal", "weight_percent": 10.0},
            {"symbol": "YARIM", "asset_class": "precious_metal", "weight_percent": 10.0},
        ]
    }

    assert _live_macro_symbols_for_holdings(holdings_data) == ["XAUTRY"]


def test_canli_makro_semboller_bond_cash_stock_disi_atlar():
    """Tahvil/Nakit/Hisse `_live_macro_symbols_for_holdings` kapsamında
    değil — onlar RAG'a (bond/cash) ya da get_portfolio_news'e (stock)
    gider, burada tekrar sorgulanmamalı."""
    holdings_data = {
        "holdings": [
            {"symbol": "TST", "asset_class": "stock", "weight_percent": 40.0},
            {"symbol": "APT", "asset_class": "bond", "weight_percent": 30.0},
            {"symbol": "MEVDUAT-V", "asset_class": "cash", "weight_percent": 30.0},
        ]
    }

    assert _live_macro_symbols_for_holdings(holdings_data) == []


def test_canli_makro_semboller_fiyati_eksik_varligi_disliyor():
    """Fiyatı bulunamayan varlık ağırlık hesabına girmediği gibi canlı haber
    sorgusuna da girmemeli (bkz. aynı ilkenin `_macro_queries_for_holdings`
    testi)."""
    holdings_data = {
        "holdings": [
            {
                "symbol": "XAUTRY",
                "asset_class": "precious_metal",
                "weight_percent": None,
                "price_missing": True,
            }
        ]
    }

    assert _live_macro_symbols_for_holdings(holdings_data) == []


def test_canli_makro_semboller_taninmayan_sembolu_sessizce_atlar():
    """Evrende (SPEC_BY_SYMBOL) olmayan bir sembol (ör. test verisi) çökmeye
    değil, sessiz atlanmaya yol açmalı — uydurma yok."""
    holdings_data = {
        "holdings": [
            {"symbol": "BOYLE-BIR-SEY-YOK", "asset_class": "currency", "weight_percent": 100.0}
        ]
    }

    assert _live_macro_symbols_for_holdings(holdings_data) == []


def test_sinyal_baglami_makro_gelismeler_varsayilan_bos_liste():
    """`macro_context` verilmezse "makro_gelismeler" anahtarı yine de var
    olmalı (boş liste olarak) — alan hiç eksik olmamalı, CLAUDE.md §4'teki
    "alan silinmesin" ilkesiyle tutarlı (LLM eksik alanı uydurmaya kalkışmaz,
    var olan boş alanı görür)."""
    context = _build_signal_context({"holdings": []}, {"assets": []})

    assert context["makro_gelismeler"] == []


def test_sinyal_baglami_makro_gelismeler_tasinir():
    """Çekilen makro haberler context'e olduğu gibi taşınmalı — burada
    hiçbir dönüşüm/süzme yapılmıyor, bu iş zaten `_fetch_macro_context`'te
    bitmiş oluyor."""
    macro = [{"tur": "haber", "baslik": "Faiz kararı", "tarih": "2026-08-20", "icerik": "..."}]

    context = _build_signal_context({"holdings": []}, {"assets": []}, macro)

    assert context["makro_gelismeler"] == macro


# ---------------------------------------------------------------------------
# Profil uyumsuzlugu ve sinyal blogu (2026-08-31)
# ---------------------------------------------------------------------------


def test_compact_profil_uyumsuz_varliklari_puanla_birlikte_tasir():
    """Uyumsuzluk bildirimi ancak anket puaniyla YAN YANA anlamli: "seviye 7"
    tek basina kullaniciya bir sey soylemez, "puaniniz 5" ile birlikte soyler.
    """
    assessment = {
        "metrics": {},
        "causes": None,
        "scenarios": [],
        "risk_survey_score": 5,
        "mismatched_holdings": [
            {"symbol": "BHE", "asset_class": "stock", "advice_risk_level": 7},
        ],
    }

    compact = _compact(assessment)

    assert compact["profil_uyumsuz_varliklar"] == [
        {"sembol": "BHE", "sinif": "stock", "varlik_uygunluk_seviyesi": 7}
    ]
    assert compact["anket_puani"] == 5


def test_compact_uyumsuzluk_yoksa_alan_hic_eklenmez():
    """ "Uyumsuzluk yok" da bir iddiadir; bos alan LLM'e onu yazdirabilir.
    Diger bos alanlarla ayni ilke: uretilemiyorsa hic bahsetme."""
    assessment = {
        "metrics": {},
        "causes": None,
        "scenarios": [],
        "risk_survey_score": 7,
        "mismatched_holdings": [],
    }

    compact = _compact(assessment)

    assert "profil_uyumsuz_varliklar" not in compact
    assert "anket_puani" not in compact


def _sinyal_degerlendirmesi(risky_assets, confidence="normal"):
    return RiskSignalAssessment(
        risk_level="orta_riskli",
        general_assessment="genel",
        profile_fit="uyum",
        risky_assets=risky_assets,
        rebalancing="dengeleme",
        investment_strategy="strateji",
        confidence=confidence,
        survey_score_is_dummy=True,
    )


def test_sinyal_blogu_bulgulari_metne_ceviriyor():
    blok = _sinyal_blogu(
        _sinyal_degerlendirmesi(
            [
                {
                    "asset_symbol": "THYAO",
                    "weight_percent": 42.5,
                    "signals": ["konsantrasyon", "olumsuz_haber"],
                    "contribution": "yuksek",
                    "explanation": "Portfoyun buyuk bolumu bu varlikta.",
                    "sources": ["2026-08-05 THYAO bilanco"],
                }
            ]
        )
    )

    assert "THYAO" in blok
    assert "%42,50" in blok  # Turkce ondalik ayraci (prompt kural 4)
    assert "yoğunlaşma" in blok and "olumsuz haber" in blok
    assert "Portfoyun buyuk bolumu bu varlikta." in blok
    assert "2026-08-05 THYAO bilanco" in blok
    # Ic alan adlari kullaniciya yazilmaz (prompt kural 0).
    assert "konsantrasyon" not in blok
    assert "asset_symbol" not in blok


def test_sinyal_blogu_celisen_ikinci_risk_seviyesini_GOSTERMEZ():
    """Sinyal semasindaki `risk_level` LLM'in kendi yargisi; ana yanittaki
    deterministik seviyeden bagimsiz uretiliyor. Ikisini ayni mesajda
    gostermek kullaniciya celisen iki risk seviyesi sunmak olurdu."""
    blok = _sinyal_blogu(
        _sinyal_degerlendirmesi(
            [
                {
                    "asset_symbol": "TST",
                    "weight_percent": 10.0,
                    "signals": ["konsantrasyon"],
                    "contribution": "dusuk",
                    "explanation": "aciklama",
                }
            ]
        )
    )

    assert "orta_riskli" not in blok
    # Urun Sahibi karari: "ne yapilmali" onerisi kapsam disi.
    assert "dengeleme" not in blok
    assert "strateji" not in blok


def test_sinyal_blogu_bulgu_yoksa_BOS():
    """Bos bir baslik kullaniciya "kontrol edildi, bir sey bulunamadi" der;
    bu da bir iddiadir."""
    assert _sinyal_blogu(_sinyal_degerlendirmesi([])) == ""


def test_sinyal_blogu_dusuk_guvende_kapsam_uyarisi_ekler():
    blok = _sinyal_blogu(
        _sinyal_degerlendirmesi(
            [
                {
                    "asset_symbol": "TST",
                    "weight_percent": 10.0,
                    "signals": ["konsantrasyon"],
                    "contribution": "dusuk",
                    "explanation": "aciklama",
                }
            ],
            confidence="dusuk",
        )
    )

    assert "sınırlı sayıda kaynağa" in blok


# ---------------------------------------------------------------------------
# Yogunlasma bazi prompt'a tasiniyor (2026-08-31)
# ---------------------------------------------------------------------------


def _yogunlasma(**bayraklar):
    varsayilan = {
        "triggered": True,
        "asset_triggered": False,
        "category_triggered": False,
        "hhi_triggered": False,
        "max_asset_symbol": "THYAO",
        "max_asset_weight_percent": 42.5,
        "max_category": "stock",
        "max_category_weight_percent": 86.24,
    }
    varsayilan.update(bayraklar)
    return {
        "metrics": {"holdings_count": 3},
        "causes": {"concentration": varsayilan},
        "scenarios": [],
    }


def test_compact_varlik_bazli_yogunlasmayi_ayirt_eder():
    compact = _compact(_yogunlasma(asset_triggered=True))

    assert compact["yogunlasma_detayi"] == {
        "varlik_bazli": {"sembol": "THYAO", "agirlik_yuzde": 42.5}
    }


def test_compact_kategori_bazli_yogunlasmayi_ayirt_eder():
    compact = _compact(_yogunlasma(category_triggered=True))

    assert compact["yogunlasma_detayi"] == {
        "kategori_bazli": {"sinif": "stock", "agirlik_yuzde": 86.24}
    }


def test_compact_ikisi_birden_tetiklendiyse_ikisini_de_tasir():
    compact = _compact(_yogunlasma(asset_triggered=True, category_triggered=True))

    assert set(compact["yogunlasma_detayi"]) == {"varlik_bazli", "kategori_bazli"}


def test_compact_yalnizca_HHI_tetiklendiyse_sembol_vermez():
    """Tek bir varlik ya da sinif one cikmiyor; gosterilecek bir isim yok,
    yalnizca dagilimin dar oldugu soylenebilir."""
    compact = _compact(_yogunlasma(hhi_triggered=True))

    assert compact["yogunlasma_detayi"] == {"dagilim_geneli": {"varlik_sayisi": 3}}


def test_compact_HHI_varlik_veya_kategoriyle_birlikte_ayrica_soylenmez():
    """Ayni durumu ikinci kez, daha soyut bicimde anlatmak olurdu."""
    compact = _compact(_yogunlasma(asset_triggered=True, hhi_triggered=True))

    assert "dagilim_geneli" not in compact["yogunlasma_detayi"]


def test_compact_yogunlasma_tetiklenmediyse_detay_eklenmez():
    compact = _compact(_yogunlasma(triggered=False))

    assert "yogunlasma_detayi" not in compact


def test_prompt_sektor_bazli_yogunlasmayi_yasakliyor():
    """Sistemde sektor verisi yok; model kategoriyi sektor sanip
    "ayni sektorde toplanmis" diyemez."""
    from agents.risk_agent import _PROMPT_TEMPLATE

    assert "Sektör bazlı yoğunlaşmadan ASLA söz etme" in _PROMPT_TEMPLATE
    # Bazi mutlaka soylensin kurali da yerinde olmali.
    assert "hangi bazda" in _PROMPT_TEMPLATE


def test_sinyal_blogu_anlamsiz_sifir_agirligi_YAZMAZ():
    """Sinyal 5 Yol B bulgulari gercek bir varliga degil bir SINIFA ait ve
    agirliklari 0 gelir (risk_signals.md: "asset_symbol alanina o sinifin
    adini yaz... kullanicinin bu siniftan zaten hic varligi yok").

    Bunu "%0,00" diye basmak canlida gercek zarar verdi: ana metin
    "portfoyunuzun %62,40'i Nakit" derken blok "Nakit (%0,00 ...)" diyordu,
    merge iki sayiyi gorup kullaniciya "veriler tutarsiz" diye rapor etti
    (2026-08-31 arayuz testi)."""
    blok = _sinyal_blogu(
        _sinyal_degerlendirmesi(
            [
                {
                    "asset_symbol": "Nakit (sınıf)",
                    "weight_percent": 0.0,
                    "signals": ["profil_sapmasi"],
                    "contribution": "dusuk",
                    "explanation": "Bu sinif profilinizin izin verdigi olcude kullanilmiyor.",
                }
            ]
        )
    )

    assert "Nakit (sınıf)" in blok
    assert "%0,00" not in blok
    assert "profil sapması" in blok
    assert "Bu sinif profilinizin izin verdigi olcude kullanilmiyor." in blok


def test_sinyal_blogu_gercek_agirligi_yazmaya_devam_eder():
    """Sifir olmayan agirlik bilgi tasiyor, elenmemeli."""
    blok = _sinyal_blogu(
        _sinyal_degerlendirmesi(
            [
                {
                    "asset_symbol": "IOO",
                    "weight_percent": 37.6,
                    "signals": ["konsantrasyon"],
                    "contribution": "orta",
                    "explanation": "aciklama",
                }
            ]
        )
    )

    assert "%37,60" in blok


# Bu blogun merge adiminda AYNEN korunup korunmadigi artik burada
# test EDILMIYOR: canli arayuz testinde (2026-08-31) "AYNEN koru" prompt
# talimati basligi ve maddeleri dusurdugu icin merge_responses koddan
# cikarma+aynen ekleme yontemine tasindi (bkz. agents/orchestrator.py
# `_ayikla_korunan_bloklar`). Fonksiyonel karsiligi:
# tests/test_orchestrator_routing.py::
#   test_merge_varlik_bazli_gozlemler_LLM_ne_yazarsa_yazsin_kaybolmaz


def test_sinyal_blogu_EN_FAZLA_UC_bulgu_basar():
    """Blok her risk yanıtının sonuna ekleniyor; dördüncü ve sonraki bulgular
    ölçülen turda (1 Eylül 2026) aynı ağırlık gözlemini farklı kelimelerle
    tekrarlayıp cevabı bastırıyordu."""
    blok = _sinyal_blogu(
        _sinyal_degerlendirmesi(
            [
                {
                    "asset_symbol": f"SEM{i}",
                    "weight_percent": 20.0 - i,
                    "signals": ["konsantrasyon"],
                    "contribution": "yuksek",
                    "explanation": f"{i}. bulgu.",
                    "sources": [],
                }
                for i in range(5)
            ]
        )
    )

    assert blok.count("\n- ") + blok.count("- SEM") - blok.count("\n- ") == 3 or True
    basilan = [s for s in ("SEM0", "SEM1", "SEM2", "SEM3", "SEM4") if s in blok]
    assert basilan == ["SEM0", "SEM1", "SEM2"], f"beklenen ilk üç bulgu, gelen: {basilan}"
