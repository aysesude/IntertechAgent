"""Risk/Strateji Ajanı: MCP `get_risk_assessment` tool'unu çağırır, dönen
değerlendirmeyi LLM ile doğal dile döker.

Portföy Ajanı'yla aynı kalıp: sayısal hiçbir değer LLM tarafından üretilmez —
volatilite, VaR, Sharpe ve yeniden dengeleme senaryolarının tamamı
`app/services/risk_service.py`'de hesaplanır, LLM yalnızca özetler.

Tool'un tam sözleşmesi: docs/MCP-TOOLS.md · metodoloji: gerek.md FR-4.
"""

import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from agents.base import AgentRequest, AgentResponse, BaseAgent
from app.core.config import (
    RISK_MAX_CATEGORY_WEIGHT,
    RISK_TARGET_VOLATILITY_BAND,
    RiskProfile,
)
from app.core.llm_client import get_llm_client

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "risk_agent.md").read_text(encoding="utf-8")

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


class RiskAgent(BaseAgent):
    agent_name = "risk_agent"

    async def execute(
        self, request: AgentRequest, *, on_token: Callable[[str], None] | None = None
    ) -> AgentResponse:
        tool_result = await self.call_mcp_tool(
            "get_risk_assessment",
            {"user_id": request.user_id, "include_scenarios": _wants_scenarios(request.query)},
        )

        if not tool_result.get("success"):
            error = tool_result.get("error", {})
            return self.error_response(error.get("message", "Risk değerlendirmesi alınamadı"))

        data = tool_result["data"]
        summary_text = await self._summarize(request.query, data, on_token=on_token)
        return AgentResponse(
            agent_name=self.agent_name, success=True, summary_text=summary_text, data=data
        )

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
