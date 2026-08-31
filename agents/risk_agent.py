"""Risk/Strateji Ajanı: MCP `get_risk_assessment` tool'unu çağırır, dönen
değerlendirmeyi LLM ile doğal dile döker.

Portföy Ajanı'yla aynı kalıp: sayısal hiçbir değer LLM tarafından üretilmez —
volatilite, VaR, Sharpe ve yeniden dengeleme senaryolarının tamamı
`app/services/risk_service.py`'de hesaplanır, LLM yalnızca özetler.

Tool'un tam sözleşmesi: docs/MCP-TOOLS.md · metodoloji: gerek.md FR-4.

2026-08-22 eki — Sinyal tabanlı risk değerlendirmesi (bkz. Google Drive
"Intertech - Ekip 3", "riskk" bölümü, iş analisti güncellemesi). Bu YUKARIDAKİ
volatilite tabanlı akışın YERİNE GEÇMEZ — iş analistiyle netleştirildi: ikisi
ayrı, birbirinden bağımsız iki metrik seti. Aşağıdaki `_assess_signals` ve
ilgili yardımcılar TAMAMEN AYRI bir yol izler: hiçbir sayı kod tarafında
hesaplanmaz/sınıflandırılmaz, girdi yalnızca portföy ağırlıkları ve
`get_portfolio_news`'ten gelen haber/bilanço/yorum parçalarıdır; risk
seviyesini ve tüm metni LLM üretir (bkz. agents/prompts/risk_signals.md).

Dummy anket puanı (KALDIRILDI, bkz. 2026-08-26 eki): bu paragraf yazıldığında
1-7 arası gerçek anket henüz yoktu. ARTIK VAR — bkz. 2026-08-26 eki, alt
paragraf: `users.risk_survey_score` gerçek, migrate edilmiş, test edilmiş bir
alan (`set_user_risk_survey`, `RISK_SURVEY_SCORE_TO_PROFILE`); "anket yok"
DEĞİL, eksik olan yalnızca anketin YENİDEN DOLDURULDUĞU ANI (event) yakalayan
bir mekanizma — bkz. docs/notes/sinyal5-olay-tabanli-aktivasyon-tasarimi.md.
Bu paragraf yalnızca o zamanki `_DUMMY_SURVEY_SCORE_BY_PROFILE` kaldırma
kararının tarihsel gerekçesi olarak duruyor. Önceki sürümde
`_DUMMY_SURVEY_SCORE_BY_PROFILE` mevcut
4'lü `RiskProfile`'dan GEÇİCİ bir 1-7 değeri türetiyor, Sinyal 5 bunu
"elindeki varlık sınıfı ŞU ANKİ dummy puanla izinli mi" şeklinde her sohbet
turunda pasifçe kontrol ediyordu. Bu yaklaşım analistin son netlemesiyle
tamamen kaldırıldı.

2026-08-24 eki — Doküman yeniden okundu ("riskk" bölümü genişletildi).
Değişenler: (1) `RiskSignalFinding` artık `signals` (liste, tekten çoğula) +
`contribution` alanı taşıyor (bkz. app/schemas/risk_signals.py). (2) Sinyal 5
(profil_sapmasi) artık netçe "elindeki varlık sınıfı ŞU ANKİ dummy puanla
izinli mi" karşılaştırmasına bağlandı — "kullanıcı anketi yeniledi" alt
durumu gerçek anket geçmişi olmadan TESPİT EDİLEMEZ, bu iş analistine
iletildi. (3) Makro haber entegrasyonu eklendi (`_fetch_macro_context`):
Tahvil/Döviz/Altın/Nakit sınıflarının şirket bilançosu olmadığı için
`get_portfolio_news` bu sınıflarda neredeyse hiç doküman döndürmüyor —
doküman bu sınıflar için haber kaynağının makro/piyasa haberleri olduğunu
belirtiyor. Bu haberler yalnızca `investment_strategy` metnini besler,
sinyal tetiklemek (kaynak sayılmak) için KULLANILMAZ — bkz.
agents/prompts/risk_signals.md.

2026-08-25 eki — Canlı veri genişlemesi. Doküman "riskk" bölümü, "market
research ajanı" bölümü ve "next toplantıda sorulacaklar" (live'a çıkacak mı?)
birlikte incelendi: dokümanın kendi "market ajanı" tasarımı (KAP + canlı
haber API + MCP/Web Search, intent bazlı yönlendirme) hiçbir altyapısı
olmayan, takımın kendisinin "açık soru" işaretlediği geniş bir mimari — yeni
bir haber API'si/KAP scraper edinmek analiste sormadan tek başına
verilebilecek bir karar değil (ücret + altyapı kararı).
Bunun yerine DAR ve BUGÜN yapılabilir bir alt küme uygulandı: proje zaten
yfinance kullanıyor (ücretsiz, anahtarsız); Döviz ve Kıymetli Maden'in
yfinance'te gerçek ticker'ı var (bkz. app/providers/universe.py). Bunlar için
`data/macro_news_update.py` (price_service.py'deki "canlı çağrı sohbet anını
bloklamasın" ilkesiyle, GÜNLÜK BATCH olarak) canlı haber çekip
`macro_news_snapshot`a yazıyor; `_fetch_macro_context` bunu `get_macro_news`
ile OKUYOR, portföydeki GERÇEK sembole göre kişiselleştirilmiş. Tahvil/Nakit
için yfinance'te ticker yok — onlar RAG'daki (donmuş, 2026-08-20'den beri
yeni eklenmeyen) makro dokümanlarda kalmaya devam ediyor; bu bilinen bir
sınırlama olarak kabul edildi, analiste iletilmedi (maliyet/altyapı kararı
gerektirmiyor).

2026-08-26 eki — Sinyal 5 (profil_sapmasi) analistle son kez netleşti:
"sinyal 5 ağırlıklara bakmasın, sadece anketi yeniden doldurduğunda
tetiklensin" (önce ekip liderinin, sonra analistin onayladığı nihai cevap).
Bu, önceki iki yaklaşımın da ARTIK GEÇERSİZ olduğu anlamına geliyor: (1)
riskk dokümanındaki örnekteki %25 tavan/ağırlık eşiği, (2) bu dosyanın az
önce uyguladığı "elindeki sınıf ŞU ANKİ dummy puanla izinli mi" pasif
kontrolü — ikisi de ya ağırlığa bakıyordu ya da her sohbet turunda pasifçe
tetikleniyordu, ikisi de istenen bu değil. `_DUMMY_SURVEY_SCORE_BY_PROFILE`,
`_dummy_survey_score()` ve context'teki `survey_puani_dummy`/
`survey_puani_dummy_uyarisi`/`bu_puanla_izinli_siniflar` alanları bu yüzden
KALDIRILDI (bkz. `_build_signal_context`, `_assess_signals`). Gerçek anket
YENİDEN DOLDURMA olayını (event) yakalayan bir mekanizma — ör.
`user_service.set_user_risk_profile`'ın ne zaman, hangi eski değerden hangi
yeni değere çağrıldığını bilen bir yapı — projede henüz YOK; eklenene kadar
Sinyal 5 kalıcı olarak DORMANT'tır (LLM'e hiç kullanmaması söyleniyor, bkz.
agents/prompts/risk_signals.md).

2026-08-28 eki — Sinyal 5 kapsamı GENİŞLETİLDİ, 2026-08-26'daki karar
DARALTILMADI. Analist netleşti: sinyal "yeniden doldurulduğunda VE risk
kapasitesi kullanılmadığında" tetiklensin — yani iki BAĞIMSIZ yol var, Yol A
(2026-08-26'daki olay tabanlı yol, hâlâ geçerli, hâlâ dormant çünkü olay
mekanizması yok) ve Yol B (yeni: portföy profile göre gereğinden temkinliyse
bilgilendirme tonunda bir bulgu — bu yolun OLAY beklemesi gerekmiyor, şu anki
`risk_survey_score` + holdings yeterli, dolayısıyla Yol A'nın altyapısını
beklemeden uygulanabilir). Tasarımın tamamı, açık kalan tek belirsizlik
(Yol B'nin "kapasite" tanımı `advice_eligibility` mi yoksa
`RISK_MAX_CATEGORY_WEIGHT` mi olduğu) dahil:
docs/notes/sinyal5-olay-tabanli-aktivasyon-tasarimi.md. Kod tarafı HENÜZ
YAZILMADI — bu ek yalnızca tasarım/kapsam kararını yansıtıyor.

2026-08-28 eki (kod) — Yol A'nın kod tarafı yazıldı (tasarım belgesi §4.1-4.7):
`users.risk_survey_updated_at`/`risk_survey_event_consumed_at` kolonları
(migration `e2a7c9f14d68`), `user_service.get_and_consume_risk_survey_event`
ve onu saran MCP tool'u `get_risk_survey_event` eklendi.
`_assess_signals` artık `get_holdings`/`get_portfolio_news`'in yanına ÜÇÜNCÜ
bir çağrı olarak bu tool'u da çağırıyor; yalnızca `olay_var: true` VE
`izin_verilmeyen_ve_elde_olan_siniflar` BOŞ DEĞİLSE `_build_signal_context`'e
`anket_yeniden_dolduruldu`/`yeni_profille_izinsiz_kalan_siniflar` alanları
geçiriliyor — aksi hâlde (olay yok, ya da olay var ama ihlal yok) context bu
alanları hiç TAŞIMIYOR, önceki "üretilemiyorsa hiç bahsetme" ilkesiyle
tutarlı. Tool başarısız olursa (herhangi bir nedenle) mevcut davranış aynen
sürer — bu üçüncü çağrı da diğer ikisi gibi ana yanıtı BLOKE ETMEZ.

2026-08-28 eki (Yol B kod) — Analist "hangi kapasite" sorusunu netleştirdi:
"risk seviyesi yüksek çıktı ama daha az riskli varlıkları var" — yani (a)
yorumu, `advice_eligibility.allowed_asset_classes`. Yol B'nin kod tarafı
(tasarım belgesi §4.8-4.10) yazıldı: yeni saf fonksiyon
`_kullanilmayan_kapasite(holdings_data, risk_survey_score)` — hiçbir OLAYA
ihtiyaç duymaz, `_assess_signals`'a zaten giden `assessment_data`'daki
(FR-4/volatilite yanıtı) `risk_survey_score` ile mevcut holdings'in farkını
alır. `risk_survey_score` `None` ise (anket hiç doldurulmamış) boş liste
döner. Sonuç doluysa `_build_signal_context`'e `kullanilmayan_kapasite`
alanı geçiriliyor; boşsa/None ise context'e hiç eklenmiyor — Yol A'yla aynı
"üretilemiyorsa hiç bahsetme" ilkesi. Yol A'nın "azaltıcı" (ihlal) yönüyle bu
yolun "artırıcı/bilgilendirici" yönü aynı sinyal kodu (`profil_sapmasi`)
altında ama prompt'ta FARKLI TONDA ele alınıyor (bkz. risk_signals.md).

2026-08-31 eki (Yağız) — "risk seviyem nedir" sorusu artık portföyün
tamamını anlatıyor. Değişenler:

(1) `_assess_signals` HER risk sorusunda çalışıyor. Önceden `_wants_scenarios`
    kapısının arkasındaydı; soruda "dengele/azalt/öneri/strateji/ne yapmalı"
    köklerinden biri geçmiyorsa hiç çağrılmıyordu — yani "portföyümün risk
    seviyesi nedir" gibi en sıradan soruda yoğunlaşma da haber yorumu da
    üretilmiyordu. `_wants_scenarios` yalnızca tool'un `include_scenarios`
    parametresi için kullanılmaya devam ediyor.

(2) Sonucu artık `summary_text`'e giriyor (`_sinyal_blogu`). Önceden yalnızca
    `response_data["risk_signal_assessment"]`'a yazılıyordu; o alanı repoda
    hiçbir yer okumuyor ve `orchestrator.merge_responses` yalnızca
    `summary_text`'i topluyor — üretilen değerlendirme fiilen atılıyordu.
    Blokta bilinçli olarak yalnızca `risky_assets` gösteriliyor; gerekçe
    `_sinyal_blogu` docstring'inde.

(3) Profil uyumsuzluğu (elde olan ama anket puanının izin vermediği varlık)
    artık DETERMİNİSTİK olarak ana yanıtta: `risk_service` bunu
    `RiskAssessment.mismatched_holdings` alanında taşıyor (portföy ve puan
    orada zaten yüklü), `_compact` prompt'a geçiriyor. LLM'in takdirine
    bağlı DEĞİL — Sinyal 5'in tersine her zaman görünür.

BİLİNEN YAN ETKİ: `get_risk_survey_event` tüketen bir tool ve artık her risk
sorusunda çağrılıyor, dolayısıyla anket olayı daha erken tüketiliyor. Sinyal
5 Yol A bulgusu artık metne girdiği için tüketim ile gösterim aynı turda
oluyor; yine de LLM o bulguyu üretmezse olay görünmeden harcanır. Bu risk
(3)'teki deterministik yol sayesinde kullanıcı açısından telafi ediliyor:
uyumsuzluk bilgisi olaydan bağımsız olarak her zaman veriliyor."""

import json
import logging
import re
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agents.base import AgentRequest, AgentResponse, BaseAgent
from app.core.config import (
    RISK_MAX_CATEGORY_WEIGHT,
    RISK_TARGET_VOLATILITY_BAND,
    RiskProfile,
)
from app.core.llm_client import get_llm_client
from app.providers.universe import SPEC_BY_SYMBOL, macro_news_key
from app.schemas.risk_signals import RiskSignalAssessment
from app.services.advice_eligibility import allowed_asset_classes

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "risk_agent.md").read_text(encoding="utf-8")
_SIGNAL_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "risk_signals.md").read_text(
    encoding="utf-8"
)

# 2026-08-26: _DUMMY_SURVEY_SCORE_BY_PROFILE / _dummy_survey_score() BURADAN
# KALDIRILDI — bkz. modül docstring'i "2026-08-26 eki". Sinyal 5 artık
# profil tabanlı dummy puana hiç bakmıyor; anket-yeniden-doldurma OLAYINI
# yakalayan gerçek bir mekanizma gelene kadar kalıcı olarak dormant.
_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


# Şirket bilançosu olmayan sınıflar için haber kaynağı makro piyasa
# haberleridir (bkz. modül docstring'i, 2026-08-24 eki). STOCK burada YOK:
# hisse zaten get_portfolio_news ile sembol bazlı kapsanıyor, ayrıca makro
# sorgu eklemek gürültü + gereksiz RAG çağrısı olurdu.
#
# 2026-08-25 eki: yalnızca BOND ve CASH burada kalıyor. CURRENCY ve
# PRECIOUS_METAL artık RAG'daki (donmuş) makro dokümanları DEĞİL,
# `get_macro_news` üzerinden CANLI ve portföye göre kişiselleştirilmiş
# (yalnızca tutulan sembol) haber alıyor — bkz. `_live_macro_symbols_for_holdings`
# ve app/services/macro_news_ingest.py modül docstring'i (neden bu ayrım:
# yfinance'te yalnızca bu iki sınıfın gerçek ticker'ı var; Tahvil/Nakit'in
# yok, RAG'daki mevcut TCMB/enflasyon dokümanları onlar için tek kaynak
# olmaya devam ediyor).
_MACRO_QUERY_BY_ASSET_CLASS: dict[str, str] = {
    "bond": "faiz kararı tahvil piyasası getiri görünümü",
    "cash": "enflasyon faiz oranı mevduat piyasası görünümü",
}

# `_live_macro_symbols_for_holdings`'in kapsadığı sınıflar — yalnızca bunlar
# `get_macro_news`'e (canlı) gider, geri kalanı `_MACRO_QUERY_BY_ASSET_CLASS`
# üzerinden RAG'a (bkz. yukarıdaki not).
_LIVE_MACRO_ASSET_CLASSES = frozenset({"currency", "precious_metal"})


def _macro_queries_for_holdings(holdings_data: dict[str, Any]) -> list[str]:
    """Portföyde fiilen TUTULAN, RAG'a gidecek (Tahvil/Nakit) sınıflar için
    hangi makro haber sorgularının çalıştırılacağını belirler.

    Yalnızca portföyde gerçekten bulunan sınıflar sorgulanır (tutulmayan bir
    sınıf için RAG çağrısı yapmak gereksiz gecikme + alakasız gürültüdür).
    Sıra `_MACRO_QUERY_BY_ASSET_CLASS` tanım sırasını izler ki sonuç
    deterministik olsun (testte kırılgan sıralamaya bağlı kalınmasın)."""
    held_classes = {
        h.get("asset_class")
        for h in holdings_data.get("holdings", [])
        if not h.get("price_missing")
    }
    return [
        query
        for asset_class, query in _MACRO_QUERY_BY_ASSET_CLASS.items()
        if asset_class in held_classes
    ]


def _live_macro_symbols_for_holdings(holdings_data: dict[str, Any]) -> list[str]:
    """Portföyde fiilen TUTULAN Döviz/Kıymetli Maden varlıkları için
    `get_macro_news`'e geçirilecek "haber anahtarı" listesini üretir (bkz.
    `app.providers.universe.macro_news_key`).

    Tanınmayan bir sembol (evrende olmayan, ör. test verisi) veya haber
    anahtarı üretilemeyen bir varlık (`macro_news_key` None dönerse)
    SESSİZCE atlanır — uydurma yok, yalnızca o varlık için canlı bağlam
    üretilmez. Sonuç tekilleştirilir (ör. CEYREK + YARIM ikisi de XAUTRY'ye
    düşer) ve deterministik sırayla (portföydeki varlık sırası) döner."""
    keys: list[str] = []
    seen: set[str] = set()
    for h in holdings_data.get("holdings", []):
        if h.get("price_missing") or h.get("asset_class") not in _LIVE_MACRO_ASSET_CLASSES:
            continue
        spec = SPEC_BY_SYMBOL.get(h.get("symbol"))
        if spec is None:
            continue
        key = macro_news_key(spec)
        if key is None or key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return keys


# Kök neden teşhisindeki alan adlarının kullanıcıya gösterilecek karşılıkları.
_CAUSE_LABELS = {
    "concentration": "Yoğunlaşma",
    "high_volatility_asset": "Yüksek volatiliteli varlık",
    "correlation": "Yüksek korelasyon",
}

# Senaryo üretimi ek hesaplama maliyeti getirdiği için tool'da varsayılan
# olarak kapalı; yalnızca kullanıcı gerçekten "ne yapmalıyım" diye sorduğunda
# açılır.
#
# Burada alt dizi araması bilinçli: orchestrator'ın kapsam filtresinden farklı
# olarak bu kökler uzun ve ayırt edici ("dengele" başka bir kelimenin içinde
# tesadüfen geçmez), üstelik alt dizi araması Türkçe çekim eklerini
# ("dengelemeliyim", "azaltmak") ek kod yazmadan yakalar.
_SCENARIO_STEMS = ("dengele", "azalt", "oneri", "onerir", "strateji", "iyilestir", "ne yapmali")

_FOLD_MAP = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u"})


def _wants_scenarios(query: str) -> bool:
    folded = query.replace("İ", "i").lower().translate(_FOLD_MAP)
    return any(stem in folded for stem in _SCENARIO_STEMS)


def _risk_profile(value: Any) -> RiskProfile | None:
    """Tool JSON'undaki profil değerini enum'a çevirir; tanınmazsa None."""
    try:
        return RiskProfile(value)
    except ValueError:
        return None


def _pct(ratio: Decimal) -> float:
    """Oranı yüzdeye çevirir (0.25 -> 25.0). Sunum için; hesap değil."""
    return float(ratio * 100)


def _profile_position(
    volatility_percent: float | None,
    is_within_profile: bool | None,
    band_lower_percent: float,
) -> str | None:
    """Volatilitenin profilin hedef bandına göre konumu: altında/içinde/üstünde.

    NEDEN GEREKLİ. `risk_service` yalnızca ÜST sınırı kontrol ediyor
    (`is_within_profile = volatility <= band_upper`); bandın ALTINDA kalmak
    "içinde" sayılıyor. Sonuç: Agresif profilli, %3,5 volatiliteli bir
    kullanıcıya "profilinizin içindesiniz" deniyor — beyan ettiği risk
    tercihinin çok altında durduğu hiç söylenmiyor. Ölçüldü: 50 kullanıcının
    32'si bu durumda (agresif 16, dengeli 16'nın çoğu).

    Üst sınır kararı SERVİSTEN alınır, burada yeniden hesaplanmaz — iki
    katmanın çelişmesi mümkün olmasın. Bu fonksiyon yalnızca servisin
    ayırmadığı "altında" durumunu ekler.

    Karşılaştırma kodda yapılıyor, prompt'a bırakılmıyor: modelden iki sayıyı
    karşılaştırmasını istemek, sonucu güvenilmez kılar.
    """
    if is_within_profile is None or volatility_percent is None:
        return None
    if not is_within_profile:
        return "bandin_ustunde"
    return "bandin_altinda" if volatility_percent < band_lower_percent else "band_icinde"


def _compact(data: dict[str, Any]) -> dict[str, Any]:
    """Değerlendirmenin LLM'e gidecek küçültülmüş hâlini üretir.

    Ham `RiskAssessment` korelasyon matrisi, kategori metrikleri ve senaryo
    başına varlık kırılımı taşıyor — küçük bir modele bunun tamamını vermek
    hem yavaş hem de dikkat dağıtıcı. Buradaki alan seçimi, kullanıcının
    "riskim ne durumda" sorusuna cevap veren asgari kümedir; ayrıntı isteyen
    arayüz `/api/risk` üzerinden tam veriye zaten erişiyor.

    `None` değerler KORUNUR: risk hesaplanamadığında (yetersiz fiyat geçmişi,
    boş portföy) LLM bunu görüp "hesaplanamadı" demeli — alan silinirse
    uydurmaya açık kapı bırakılır (CLAUDE.md §4).
    """
    metrics = data.get("metrics") or {}
    compact: dict[str, Any] = {
        "tarih": data.get("as_of"),
        "risk_profili": data.get("risk_profile"),
        "risk_seviyesi": data.get("risk_level"),
        # Aşağıda `profil_konumu` ile DEĞİŞTİRİLİR (hesaplanabildiği sürece).
        # İkisi birlikte gönderilmemeli: `is_within_profile` yalnızca üst sınırı
        # kontrol ettiği için bandın altındaki portföyde `true` olur ve
        # `profil_konumu="bandin_altinda"` ile yüzeyde çelişir. Canlıda model bu
        # çelişkiyi fark edip AÇIKLAMAYA çalıştı ve iç alan adlarını kullanıcıya
        # yazdı ("profil_bandinda_mi alanında 'evet' bilgisi yer alsa da...").
        "profil_bandinda_mi": data.get("is_within_profile"),
        "toplam_deger_try": data.get("total_value"),
        "yillik_volatilite_yuzde": metrics.get("annualized_volatility_percent"),
        "maksimum_dusus_yuzde": metrics.get("max_drawdown_percent"),
        "var_tutar_try": metrics.get("value_at_risk_try"),
        "var_yuzde": metrics.get("value_at_risk_percent"),
        "var_guven_yuzde": metrics.get("value_at_risk_confidence"),
        "var_ufuk_gun": metrics.get("value_at_risk_horizon_days"),
        "sharpe_orani": metrics.get("sharpe_ratio"),
        "en_buyuk_varlik": metrics.get("max_asset_symbol"),
        "en_buyuk_varlik_agirlik_yuzde": metrics.get("max_asset_weight_percent"),
        "en_buyuk_sinif": metrics.get("max_class"),
        "en_buyuk_sinif_agirlik_yuzde": metrics.get("max_class_weight_percent"),
        "varlik_sayisi": metrics.get("holdings_count"),
        "uyarilar": data.get("warnings") or [],
    }

    # Profilin beklenen sınırları. Kullanıcı "çok fazla hisse mi var" diye
    # sorduğunda cevap ancak bir ÖLÇÜTLE verilebilir; ağırlığı tek başına
    # söylemek soruyu cevapsız bırakıyordu (ölçüldü: %27,51 denip bırakılmış,
    # Korumacı profilin %25 üst sınırına hiç değinilmemiş).
    #
    # Eşikler burada HESAPLANMIYOR, config'deki tek tanımdan okunuyor; ajan
    # yalnızca taşıyor. Servis bunları ileride RiskAssessment'a eklerse bu
    # blok silinir.
    profile = _risk_profile(data.get("risk_profile"))
    if profile is not None:
        low, high = RISK_TARGET_VOLATILITY_BAND[profile]
        compact["profil_hedef_volatilite_bandi_yuzde"] = [_pct(low), _pct(high)]
        compact["profil_kategori_ust_sinirlari_yuzde"] = {
            asset_class.value: _pct(cap)
            for asset_class, cap in RISK_MAX_CATEGORY_WEIGHT[profile].items()
        }
        konum = _profile_position(
            compact["yillik_volatilite_yuzde"],
            data.get("is_within_profile"),
            _pct(low),
        )
        if konum is not None:
            # Konum üç durumu da ayırdığı için ikili alanın yerini alır; ikisi
            # birlikte gönderilirse yüzeyde çelişirler (bkz. yukarıdaki not).
            compact["profil_konumu"] = konum
            compact.pop("profil_bandinda_mi", None)

    causes = data.get("causes") or {}
    tetiklenen = [
        _CAUSE_LABELS.get(name, name)
        for name, cause in causes.items()
        if isinstance(cause, dict) and cause.get("triggered")
    ]
    if tetiklenen:
        compact["riskin_nedenleri"] = tetiklenen

    # 2026-08-31 eki: profil uyumsuzluğu. Bu bir RİSK ÖLÇÜMÜ DEĞİL — anket
    # puanının izin verdiği seviyenin üstünde bir varlığın elde tutulması
    # (bkz. app/services/advice_eligibility.py, risk_service'te hesaplanıyor
    # çünkü portföy ve puan orada zaten yüklü). Volatilite bandıyla ilgisi
    # yok: bandın İÇİNDEKİ bir portföyde de dolu olabilir.
    #
    # Anket puanı yalnızca uyumsuzluk VARSA gönderiliyor: prompt puanı tek
    # başına anlatacak bir yer değil, yalnızca "seviye 7, puanınız 5" gibi
    # bir karşılaştırma kurarken gerekiyor.
    uyumsuz = data.get("mismatched_holdings") or []
    if uyumsuz:
        compact["profil_uyumsuz_varliklar"] = [
            {
                "sembol": m.get("symbol"),
                "sinif": m.get("asset_class"),
                "varlik_uygunluk_seviyesi": m.get("advice_risk_level"),
            }
            for m in uyumsuz
        ]
        compact["anket_puani"] = data.get("risk_survey_score")

    scenarios = data.get("scenarios") or []
    if scenarios:
        compact["yeniden_dengeleme_secenekleri"] = [
            {
                "ad": s.get("label"),
                "volatilite_once_yuzde": s.get("volatility_before_percent"),
                "volatilite_sonra_yuzde": s.get("volatility_after_percent"),
                "islem_hacmi_yuzde": s.get("turnover_percent"),
            }
            for s in scenarios
        ]

    return compact


_SINYAL_BASLIGI = "\n\nVarlık bazlı gözlemler\n"

# Sinyal kodlarının kullanıcıya gösterilecek karşılıkları. Kod adları
# (`konsantrasyon`, `sektor_yogunlasmasi`) iç alan adlarıdır; risk_agent.md
# kural 0 bunların kullanıcıya yazılmasını yasaklıyor.
_SINYAL_ADLARI = {
    "konsantrasyon": "yoğunlaşma",
    "sektor_yogunlasmasi": "sektör yoğunlaşması",
    "olumsuz_haber": "olumsuz haber",
    "sektor_gelismesi": "sektör gelişmesi",
    "profil_sapmasi": "profil sapması",
}


def _sinyal_blogu(assessment: RiskSignalAssessment) -> str:
    """Sinyal değerlendirmesinin kullanıcıya GÖSTERİLECEK kısmını metne çevirir.

    NEDEN SADECE `risky_assets`. Şemadaki diğer alanlar bilinçli olarak
    DIŞARIDA bırakılıyor:

    - `risk_level`: LLM'in kendi kategorik yargısı ("orta_riskli"), ana
      yanıttaki DETERMİNİSTİK risk seviyesinden (volatiliteden gelen "Çok
      Düşük") bağımsız üretiliyor. İkisini aynı mesajda göstermek kullanıcıya
      birbiriyle çelişen iki risk seviyesi sunmak olurdu — `_compact`'teki
      `profil_bandinda_mi`/`profil_konumu` çelişkisinin aynısı.
    - `rebalancing` ve `investment_strategy`: Ürün Sahibi kararıyla (2026-08,
      bkz. `Settings.risk_scenarios_enabled` yanındaki not) "ne yapılmalı"
      önerisi ürün kapsamı dışında; risk artık yalnızca tespit/bildirim.
    - `profile_fit`: profil uyumu artık deterministik olarak ana yanıtta
      anlatılıyor (bkz. `_compact` → `profil_uyumsuz_varliklar`); LLM'in
      ikinci bir yorumunu eklemek aynı şeyi iki kez, muhtemelen farklı
      söylemek olurdu.

    Metin KOD TARAFINDA birleştiriliyor, üçüncü bir LLM çağrısı yapılmıyor;
    bulguların kendi `explanation` metinleri zaten modelden geliyor.

    Bulgu yoksa boş dize döner ve çağıran taraf hiçbir şey eklemez —
    "kontrol edildi, bir şey bulunamadı" demek de bir iddiadır ve boş bir
    başlık kullanıcıya bunu ima ederdi."""
    if not assessment.risky_assets:
        return ""

    satirlar = []
    for bulgu in assessment.risky_assets:
        adlar = ", ".join(_SINYAL_ADLARI.get(s.value, s.value) for s in bulgu.signals)
        agirlik = f"{bulgu.weight_percent:.2f}".replace(".", ",")
        satir = f"- {bulgu.asset_symbol} (%{agirlik}, {adlar}): {bulgu.explanation}"
        if bulgu.sources:
            satir += f" Kaynaklar: {', '.join(bulgu.sources)}"
        satirlar.append(satir)

    blok = _SINYAL_BASLIGI + "\n".join(satirlar)
    if assessment.confidence == "dusuk":
        blok += "\n\nBu gözlemler sınırlı sayıda kaynağa dayanıyor; " "kapsamı dar olabilir."
    return blok


def _extract_json_object(text: str) -> dict[str, Any]:
    """LLM çıktısından JSON nesnesini çıkarır. Prompt "yalnızca JSON" istiyor
    ama modeller sık sık ``` kod bloğuna sarar; bunu tolere ediyoruz, başka
    hiçbir "onarımı" (eksik alan tahmini vb.) DENEMİYORUZ — bozuksa
    `json.loads` zaten fırlatır, çağıran taraf bunu görünür bir hataya çevirir."""
    stripped = _JSON_FENCE.sub("", text.strip()).strip()
    return json.loads(stripped)


def _kullanilmayan_kapasite(
    holdings_data: dict[str, Any], risk_survey_score: int | None
) -> list[str]:
    """Sinyal 5 (profil_sapmasi) Yol B'nin girdisi — bkz. modül docstring'i
    "2026-08-28 eki (Yol B kod)", docs/notes/
    sinyal5-olay-tabanli-aktivasyon-tasarimi.md §3/§4.8.

    Yol A'nın aksine hiçbir OLAYA ihtiyaç duymaz: saf bir fonksiyondur, şu an
    geçerli anket puanı ile şu an elde olan holdings'in farkını alır —
    `allowed_asset_classes(risk_survey_score)` (izinli sınıflar) EKSİ elde
    tutulan sınıflar. Analistin 2026-08-28 teyidiyle "hangi kapasite"
    belirsizliği (a) lehine çözüldü: "risk seviyesi yüksek çıktı ama daha az
    riskli varlıkları var" — yani `advice_eligibility`, `RISK_MAX_CATEGORY_
    WEIGHT`/bandın altında kalma DEĞİL (o zaten ana akışta `_profile_position`
    ile ayrıca gösteriliyor, burada TEKRARLANMIYOR).

    `risk_survey_score` `None` ise (anket hiç doldurulmamış) boş liste döner
    — "izin verilen sınıf" kavramı anketsiz tanımsızdır, uydurma yok."""
    if risk_survey_score is None:
        return []

    izinli = allowed_asset_classes(risk_survey_score)
    elde_tutulan = {
        h.get("asset_class")
        for h in holdings_data.get("holdings", [])
        if not h.get("price_missing")
    }
    return sorted(ac.value for ac in izinli if ac.value not in elde_tutulan)


def _build_signal_context(
    holdings_data: dict[str, Any],
    news_data: dict[str, Any],
    macro_context: list[dict[str, Any]] | None = None,
    *,
    yeni_profille_izinsiz_kalan_siniflar: list[str] | None = None,
    kullanilmayan_kapasite: list[str] | None = None,
) -> dict[str, Any]:
    """LLM'e verilecek ham veriyi toplar. HİÇBİR SINIFLANDIRMA/HESAPLAMA
    yapmaz — yalnızca üç kaynaktan (holdings ağırlıkları, portföy haberleri,
    makro haberler) gelen veriyi tek bir sözlükte birleştirir. Sektör verisi
    (Sinyal 2'nin ön koşulu) bilerek YOK — henüz üretilmedi (ekipte Çağan'ın
    görevi); prompt bunun yokluğunu Sinyal 2'yi atlayarak ele almalı, burada
    uydurulmaz.

    2026-08-26: profil→dummy puan eşlemesi (Sinyal 5'in eski girdisi) BURADAN
    KALDIRILDI — bkz. modül docstring'i "2026-08-26 eki". `context` artık
    hiçbir "survey_puani_dummy"/"bu_puanla_izinli_siniflar" alanı taşımıyor;
    risk_signals.md Sinyal 5'i şu an için kalıcı dormant kabul ediyor.

    2026-08-28 eki (kod): `yeni_profille_izinsiz_kalan_siniflar` — Sinyal 5
    Yol A'nın girdisi (bkz. modül docstring'i "2026-08-28 eki (kod)"). YALNIZCA
    çağıran taraf (`_assess_signals`) gerçek bir olay TESPİT ETTİĞİNDE (olay
    var VE liste boş değil) verilir; `None`/boş liste geçilirse
    `anket_yeniden_dolduruldu`/`yeni_profille_izinsiz_kalan_siniflar`
    anahtarları context'e HİÇ EKLENMEZ — "üretilemiyorsa hiç bahsetme"
    ilkesiyle tutarlı, sahte bir "olay yok" işareti (ör. boş liste) LLM'e
    "bir şey kontrol edildi ama bulunamadı" izlenimi vermesin diye.

    2026-08-28 eki (Yol B kod): `kullanilmayan_kapasite` — Sinyal 5 Yol B'nin
    girdisi (bkz. modül docstring'i "2026-08-28 eki (Yol B kod)",
    `_kullanilmayan_kapasite`). Yol A'nın alanlarıyla AYNI ilkeyle:
    `None`/boş liste geçilirse context'e hiç eklenmez.

    `macro_context` opsiyonel: `None`/boş liste geçilirse "makro_gelismeler"
    anahtarı boş liste olarak eklenir (prompt bunu görüp o bölümü boş
    bırakır, alan HİÇ eksik olmaz — CLAUDE.md §4'teki "alan silinmesin"
    ilkesiyle tutarlı)."""
    context: dict[str, Any] = {
        "varliklar": [
            {
                "sembol": h.get("symbol"),
                "sinif": h.get("asset_class"),
                "agirlik_yuzde": h.get("weight_percent"),
            }
            for h in holdings_data.get("holdings", [])
            if not h.get("price_missing")
        ],
    }

    haberler: dict[str, list[dict[str, Any]]] = {}
    for asset in news_data.get("assets", []):
        haberler[asset["symbol"]] = [
            {
                "tur": doc.get("tur"),
                "baslik": doc.get("baslik"),
                "tarih": doc.get("tarih"),
                "kaynak": doc.get("kaynak"),
                "icerik": doc.get("content"),
            }
            for doc in asset.get("documents", [])
        ]
    context["haberler"] = haberler
    context["haber_kapsami_olmayan_varliklar"] = news_data.get("assets_without_documents", [])
    context["haber_guven_duzeyi"] = news_data.get("confidence")
    # Belirli bir varlığa değil genele/sektöre ait — bilinçli olarak
    # "haberler"in DIŞINDA, ayrı bir anahtarda. Prompt bunu yalnızca
    # investment_strategy için kullanır, sinyal kaynağı SAYMAZ (bkz.
    # risk_signals.md).
    context["makro_gelismeler"] = macro_context or []

    if yeni_profille_izinsiz_kalan_siniflar:
        context["anket_yeniden_dolduruldu"] = True
        context["yeni_profille_izinsiz_kalan_siniflar"] = yeni_profille_izinsiz_kalan_siniflar

    if kullanilmayan_kapasite:
        context["kullanilmayan_kapasite"] = kullanilmayan_kapasite

    return context


def _render_signal_prompt(context: dict[str, Any]) -> str:
    """`_SIGNAL_PROMPT_TEMPLATE`'i bağlamla doldurur.

    DİKKAT: `.format()` DEĞİL, `.replace()` kullanılıyor. Bu prompt'un
    (risk_agent.md'nin aksine) içinde bir JSON çıktı şeması ÖRNEĞİ var — o
    örnekteki literal `{`/`}` karakterleri `.format()`'u KIRAR (ValueError:
    unmatched '{' vb.). Tek yer tutucu olan "{context_json}" basit bir alt
    dize değişimiyle doldurulabildiği için `.replace()` hem güvenli hem
    yeterli."""
    return _SIGNAL_PROMPT_TEMPLATE.replace(
        "{context_json}", json.dumps(context, ensure_ascii=False, indent=2)
    )


class RiskAgent(BaseAgent):
    agent_name = "risk_agent"

    async def execute(
        self, request: AgentRequest, *, on_token: Callable[[str], None] | None = None
    ) -> AgentResponse:
        wants_scenarios = _wants_scenarios(request.query)
        tool_result = await self.call_mcp_tool(
            "get_risk_assessment",
            {"user_id": request.user_id, "include_scenarios": wants_scenarios},
        )

        if not tool_result.get("success"):
            error = tool_result.get("error", {})
            return self.error_response(error.get("message", "Risk değerlendirmesi alınamadı"))

        data = tool_result["data"]
        summary_text = await self._summarize(request.query, data, on_token=on_token)

        # 2026-08-31 eki: sinyal değerlendirmesi ARTIK HER RİSK SORUSUNDA
        # üretiliyor ve METNE giriyor. Öncesinde iki ayrı sebeple görünmezdi:
        #
        # (1) yalnızca `wants_scenarios` (soruda "dengele/azalt/ne yapmalı"
        #     geçiyorsa) çağrılıyordu — "portföyümün risk seviyesi nedir"
        #     gibi en sıradan soruda hiç çalışmıyordu;
        # (2) çalıştığında bile sonucu yalnızca `response_data`'ya
        #     yazılıyordu. `risk_signal_assessment` alanını repoda HİÇBİR
        #     yer okumuyor ve `orchestrator.merge_responses` yalnızca
        #     `summary_text`'i alıyor — yani çıktı üretilip atılıyordu.
        #
        # Bedeli bilinerek kabul edildi (Yağız, 2026-08-31): tur başına
        # ek get_holdings + get_portfolio_news + get_macro_news çağrısı ve
        # bir ek LLM turu. `wants_scenarios` yalnızca SENARYO istemek için
        # kullanılmaya devam ediyor (tool'un include_scenarios parametresi).
        #
        # Ana yanıtı BOZMAZ: üretilemezse (bkz. _assess_signals) ya da hiç
        # bulgu yoksa metne hiçbir şey eklenmez.
        response_data = data
        signal_assessment = await self._assess_signals(request.user_id, data)
        if signal_assessment is not None:
            response_data = {
                **data,
                "risk_signal_assessment": signal_assessment.model_dump(mode="json"),
            }
            sinyal_blok = _sinyal_blogu(signal_assessment)
            if sinyal_blok:
                summary_text += sinyal_blok
                if on_token is not None:
                    on_token(sinyal_blok)

        return AgentResponse(
            agent_name=self.agent_name, success=True, summary_text=summary_text, data=response_data
        )

    async def _assess_signals(
        self, user_id: str, assessment_data: dict[str, Any]
    ) -> RiskSignalAssessment | None:
        """Sinyal tabanlı risk değerlendirmesini üretir (bkz. modül docstring'i
        ve agents/prompts/risk_signals.md). Bu akış `execute()`'un ana
        yanıtını ASLA BLOKE ETMEZ/BOZMAZ: gerekli tool'lardan biri başarısız
        olursa, LLM çıktısı geçerli JSON değilse ya da beklenen şemaya
        uymuyorsa None döner — çağıran taraf mevcut volatilite tabanlı yanıtı
        olduğu gibi kullanıcıya döndürmeye devam eder.

        `assessment_data` (FR-4/volatilite yanıtı, `execute()`'ta zaten
        alınmış `get_risk_assessment` sonucu) 2026-08-26'dan 2026-08-28'e
        kadar burada KULLANILMIYORDU — önceki profil→dummy puan türetme yolu
        kaldırılmıştı (bkz. modül docstring'i). Yol B ile (2026-08-28 eki)
        yeniden kullanılmaya başladı: yalnızca `risk_survey_score`'u okumak
        için — `get_risk_assessment` bu alanı zaten taşıyor (bkz.
        tests/test_risk_survey_score.py::TestRiskDegerlendirmesindeTasinmasi),
        ayrı bir tool çağrısı GEREKMİYOR."""
        holdings_result = await self.call_mcp_tool("get_holdings", {"user_id": user_id})
        if not holdings_result.get("success"):
            logger.warning(
                "[AJAN] risk: sinyal degerlendirmesi atlandi, get_holdings basarisiz — %s",
                holdings_result.get("error"),
            )
            return None

        news_result = await self.call_mcp_tool("get_portfolio_news", {"user_id": user_id})
        if not news_result.get("success"):
            logger.warning(
                "[AJAN] risk: sinyal degerlendirmesi atlandi, get_portfolio_news basarisiz — %s",
                news_result.get("error"),
            )
            return None

        # Makro haberler ana akışı BLOKE ETMEZ: bulunamazsa (ör. o sınıflar
        # için RAG'de hiç doküman yoksa) sinyal değerlendirmesi yine de
        # devam eder, yalnızca investment_strategy daha az arka plana sahip
        # olur — bu bir hata değil, bkz. _fetch_macro_context.
        macro_context = await self._fetch_macro_context(holdings_result["data"])

        # Sinyal 5 (profil_sapmasi) Yol A'nın girdisi (bkz. modül docstring'i
        # "2026-08-28 eki (kod)"): bekleyen bir anket-yeniden-doldurma olayı
        # var mı. Bu üçüncü çağrı da diğer ikisi gibi ana akışı BLOKE ETMEZ —
        # başarısız olursa ya da olay yoksa/ihlal yoksa context'e ilgili
        # alanlar HİÇ EKLENMEZ (bkz. _build_signal_context).
        yeni_profille_izinsiz_kalan_siniflar: list[str] | None = None
        survey_event_result = await self.call_mcp_tool(
            "get_risk_survey_event", {"user_id": user_id}
        )
        if survey_event_result.get("success"):
            event_data = survey_event_result["data"]
            if event_data.get("olay_var"):
                yeni_profille_izinsiz_kalan_siniflar = (
                    event_data.get("izin_verilmeyen_ve_elde_olan_siniflar") or None
                )
        else:
            logger.info(
                "[AJAN] risk: anket olayi sorgusu basarisiz, Sinyal 5 Yol A bu turda atlaniyor — %s",
                survey_event_result.get("error"),
            )

        # Sinyal 5 Yol B'nin girdisi (bkz. modül docstring'i "2026-08-28 eki
        # (Yol B kod)"): hiçbir OLAYA/tool çağrısına ihtiyaç duymaz, saf bir
        # fonksiyon — `assessment_data` zaten elde (bkz. yukarıdaki docstring).
        kullanilmayan_kapasite = _kullanilmayan_kapasite(
            holdings_result["data"], assessment_data.get("risk_survey_score")
        )

        context = _build_signal_context(
            holdings_result["data"],
            news_result["data"],
            macro_context,
            yeni_profille_izinsiz_kalan_siniflar=yeni_profille_izinsiz_kalan_siniflar,
            kullanilmayan_kapasite=kullanilmayan_kapasite,
        )
        prompt = _render_signal_prompt(context)

        llm = get_llm_client()
        try:
            raw = await llm.generate(prompt)
            parsed = _extract_json_object(raw)
            # survey_score_is_dummy: 2026-08-26'dan beri HER ZAMAN True —
            # gerçek anket-yeniden-doldurma olayını yakalayan bir mekanizma
            # yok, Sinyal 5 dormant (bkz. risk_signals.md) ve bu alan asla
            # gerçek bir anket sonucunu temsil etmiyor.
            return RiskSignalAssessment(**parsed, survey_score_is_dummy=True)
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            logger.warning("[AJAN] risk: sinyal LLM ciktisi ayristirilamadi — %s", exc)
            return None

    async def _fetch_macro_context(self, holdings_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Şirket bilançosu olmayan sınıflar (Tahvil/Döviz/Altın/Nakit) için
        makro piyasa bağlamı toplar (bkz. modül docstring'i, 2026-08-24 ve
        2026-08-25 ekleri). İki ayrı kaynaktan beslenir:

        - Döviz/Kıymetli Maden → `get_macro_news` (CANLI, yfinance haber
          akışından, portföydeki GERÇEK sembole göre kişiselleştirilmiş —
          bkz. `_live_macro_symbols_for_holdings`).
        - Tahvil/Nakit → `search_market_news` (RAG, donmuş ama var olan
          mevcut makro dokümanlar — yfinance'te bu iki sınıfın ticker'ı yok).

        Her sorgu/sembol bağımsız denenir; biri `NOT_FOUND`/
        `PROVIDER_UNAVAILABLE` ile başarısız olursa yalnızca o parça atlanır
        — tüm sinyal değerlendirmesi bloklanmaz, çünkü bu veri yalnızca
        "investment_strategy" metnini besler, hiçbir sinyali TETİKLEMEZ
        (bkz. risk_signals.md)."""
        sonuclar: list[dict[str, Any]] = []
        sonuclar.extend(await self._fetch_live_macro_news(holdings_data))

        for sorgu in _macro_queries_for_holdings(holdings_data):
            search_result = await self.call_mcp_tool(
                "search_market_news", {"query": sorgu, "top_k": 3}
            )
            if not search_result.get("success"):
                logger.info(
                    "[AJAN] risk: makro sorgu sonuçsuz, atlanıyor — sorgu=%r, hata=%s",
                    sorgu,
                    search_result.get("error"),
                )
                continue
            for parca in search_result.get("data", {}).get("results", []):
                metadata = parca.get("metadata") or {}
                sonuclar.append(
                    {
                        "tur": metadata.get("tur"),
                        "baslik": metadata.get("baslik"),
                        "tarih": metadata.get("tarih"),
                        "kaynak": metadata.get("kaynak"),
                        "icerik": parca.get("content"),
                    }
                )
        return sonuclar

    async def _fetch_live_macro_news(self, holdings_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Döviz/Kıymetli Maden için `get_macro_news`den canlı haber çeker.
        Portföyde bu sınıflardan hiç yoksa (veya hiçbiri haber anahtarına
        çözülemiyorsa) tool'u HİÇ ÇAĞIRMAZ — gereksiz MCP isteği yok."""
        symbols = _live_macro_symbols_for_holdings(holdings_data)
        if not symbols:
            return []

        news_result = await self.call_mcp_tool("get_macro_news", {"symbols": symbols})
        if not news_result.get("success"):
            logger.info(
                "[AJAN] risk: canlı makro haber sonuçsuz, atlanıyor — semboller=%r, hata=%s",
                symbols,
                news_result.get("error"),
            )
            return []

        sonuclar: list[dict[str, Any]] = []
        for sembol, haberler in news_result.get("data", {}).get("news_by_symbol", {}).items():
            for haber in haberler:
                sonuclar.append(
                    {
                        "tur": "canli_piyasa_haberi",
                        "baslik": f"[{sembol}] {haber.get('headline')}",
                        "tarih": haber.get("published_at"),
                        "kaynak": haber.get("source"),
                        "icerik": None,
                    }
                )
        return sonuclar

    async def _summarize(
        self,
        query: str,
        assessment: dict[str, Any],
        *,
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        prompt = _PROMPT_TEMPLATE.format(
            query=query,
            risk_json=json.dumps(_compact(assessment), ensure_ascii=False, indent=2),
        )
        llm = get_llm_client()
        full_text = ""
        async for chunk in llm.stream(prompt):
            full_text += chunk
            if on_token is not None:
                on_token(chunk)
        return full_text
