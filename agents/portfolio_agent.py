"""Portföy Ajanı: kullanıcının sorusuna göre gerekli MCP tool'larını seçer,
çağırır ve dönen veriyi yapısal olarak taşır.

Tool seçimi LLM ile yapılır ama **anlatı üretilmez**: model yalnızca "hangi
tool, hangi argümanla" kararını verir; sayılar tool'dan gelir, cümleyi
orchestrator'ın merge adımı kurar (Akış Şemaları, Diyagram 05).

Tool açıklamaları prompt'a elle yazılmaz; `client.list_tools()` ile MCP
sunucusundan okunur — docstring'ler sözleşme gereği zaten bu iş için yazılıyor
(docs/MCP-TOOLS.md §4). Yeni bir portföy tool'u eklemek bu dosyaya dokunmayı
gerektirmez, yalnızca TOOLS listesine adını eklemek yeterlidir.

Sorumluluk sınırı (Portfolio Agent tasarım dokümanı): analiz eder ama risk
analizi onun işi değildir; haber ve RAG piyasa ajanının.

2026-08-28 eki — Profil-uygunluk bilgilendirmesi: bu, "risk analizi" (volatilite/
VaR modelleme, yalnızca `agents/risk_agent.py`'nin işi) DEĞİLDİR — kullanıcının
GÜNCEL elindeki varlıkların, GÜNCEL anket puanının izin verdiği ölçüde
tavsiye kapsamında olup olmadığının basit bir kontrolüdür
(`advice_eligibility.mismatched_holdings`), tıpkı K/Z yüzdesi gibi zaten
`get_holdings`'ten gelen veriden deterministik olarak türetilen bir gerçek.
`orchestrator.py`'nin RISK sorulmadıkça `risk_agent`'ı hiç çağırmaması
yüzünden bu bilgi başka türlü yalnızca "ne yapmalıyım" tarzı bir soruda
görünürdü — kullanıcı sadece "portföyümü göster" dediğinde bile GÜNCEL bir
profil uyumsuzluğu varsa görmesi gerekir (bkz. `advice_eligibility.py`'nin
KAPSAM notu, "sahipse profil UYUMSUZLUĞU sayılır"). Yalnızca `get_holdings`
plandaysa çalışır (bkz. `_profil_uyum_disi_varliklar`) — `get_portfolio_
summary`'nin özet dağılımı bu kontrol için KULLANILMIYOR, tutarlı tek kaynak
`get_holdings` kalsın diye.

2026-08-31 eki — SINIF düzeyinden VARLIK düzeyine taşındı
(`mismatched_asset_classes` → `mismatched_holdings`). Sınıf, tek tek
varlıkların uygunluğuna karar vermek için fazla kabaydı ve canlıda yanlış
bildiriyordu: Korumacı bir kullanıcının elindeki IOO (para piyasası fonu)
için "Borçlanma Araçları artık tavsiye kapsamında değil" deniyordu, oysa
sınıfı BOND (seviye 2) olsa da IOO'nun kendi uygunluk seviyesi 1'dir ve o
kullanıcı için uyumludur. Bildirim artık sembol + varlığın kendi seviyesi +
anket puanı ile veriliyor.
"""

import asyncio
import json
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastmcp import Client

from agents.base import AgentRequest, AgentResponse, BaseAgent
from agents.formatting import ASSET_CLASS_TR as _ASSET_CLASS_TR
from agents.formatting import tr_amount as _tr_amount
from agents.formatting import tr_date as _tr_date
from agents.formatting import tr_percent as _tr_percent
from app.core.config import AssetClass, turkey_today
from app.core.llm_client import get_llm_client
from app.services.advice_eligibility import mismatched_holdings

logger = logging.getLogger(__name__)

_PLAN_PROMPT = (Path(__file__).parent / "prompts" / "portfolio_agent.md").read_text(
    encoding="utf-8"
)

# Bu ajanın erişebildiği tool yüzeyi. Planlayıcıya yalnızca bunlar tanıtılır ve
# yalnızca bunlar çağrılabilir — model uydurursa elenir.
TOOLS = (
    "get_portfolio_summary",
    "get_holdings",
    "get_portfolio_performance",
    "get_transactions",
    "get_benchmark_comparison",
    # Bir VARLIĞIN fiyat geçmişi. MCP'de kayıtlıydı ama hiçbir ajanın tool
    # listesinde değildi, yani sohbetten erişilemiyordu: "XAUTRY'nin son 3
    # aydaki fiyat geçmişini ver" sorusu piyasa ajanına düşüp RAG'de doküman
    # aranıyor ve "bulunamadı" dönüyordu (ölçüldü, 23 Ağustos test turu).
    # Bölünme şu: sayısal veri portföy ajanında, doküman/haber piyasa
    # ajanında. Fiyat serisi sayısal veridir.
    "get_asset_price_history",
)

# Tool sonucunun `data` içinde duracağı anahtar.
_RESULT_KEY = {
    "get_portfolio_summary": "summary",
    "get_holdings": "holdings",
    "get_portfolio_performance": "performance",
    "get_transactions": "transactions",
    "get_benchmark_comparison": "benchmark",
    "get_asset_price_history": "price_history",
}

# `user_id` YALNIZCA kullanıcıya bağlı tool'lara enjekte edilir.
#
# `get_asset_price_history` portföyden bağımsız piyasa verisidir ve imzasında
# `user_id` YOKTUR ("bu tool kullanıcıyı bilmez" —
# mcp_server/tools/price_tools.py). fastmcp tanımadığı argümanı doğrulama
# hatasıyla reddediyor, yani bu tool seçildiği her seferde çağrı düşüyordu —
# üstelik ham pydantic hata metni kullanıcının ekranına kadar gidiyordu
# (`orchestrator.merge_responses` hiçbir ajan başarılı olmadığında ajanın hata
# metnini olduğu gibi akıtır).
#
# Liste elle tutuluyor ama kendi kendine bozulmuyor:
# tests/test_portfolio_agent_tools.py bu kümeyi GERÇEK tool imzalarına karşı
# doğruluyor, yani TOOLS'a yeni bir ad eklendiğinde test hatırlatır.
_USER_SCOPED_TOOLS = frozenset(TOOLS) - {"get_asset_price_history"}

# Plan başına tavan: modelin "ne olur ne olmaz hepsini çağırayım" davranışını
# engeller. Her tool ücretli token ve bir DB sorgusu demek.
_MAX_TOOLS_PER_PLAN = 3

# Plan üretilemezse veya hiçbiri geçerli değilse: en ucuz ve en genel tool.
_FALLBACK_PLAN = [("get_portfolio_summary", {})]

# İstemci tarafında oluşan hatanın metni kullanıcıya GİTMEZ. Sunucu tarafında
# `@tool_handler` bunu zaten yapıyor; istemcide kopan bir çağrının istisna
# metni ise (bağlantı adresi, pydantic doğrulama izi) doğrudan merge adımına,
# oradan ekrana düşüyordu. Sunucudaki karşılığıyla AYNI cümle —
# mcp_server/tools/_base.py `DEFAULT_MESSAGES[INTERNAL_ERROR]`; ikinci bir
# metin yazmak aynı durumu iki ayrı cümleyle anlatırdı. Ayrıntı loga gider.
_CLIENT_ERROR_MESSAGE = "Beklenmeyen bir sorun oluştu, isteğiniz tamamlanamadı."

_HISTORY_TURNS = 4

# Küçük modeller JSON'un etrafına açıklama veya kod çiti ekliyor; Luna bunu
# genelde yapmıyor ama ayıklama ucuz ve sağlayıcı değişince yine lazım olur.
_JSON_ARRAY = re.compile(r"\[.*\]", re.DOTALL)

# Tool kataloğu çalışma anında değişmiyor; her istekte list_tools() çağırmak
# gereksiz bir tur.
_catalog_cache: str | None = None


class PortfolioAgent(BaseAgent):
    agent_name = "portfolio_agent"

    async def execute(
        self, request: AgentRequest, *, on_token: Callable[[str], None] | None = None
    ) -> AgentResponse:
        """`on_token` kullanılmıyor: ajanlar akıtmıyor, anlatıyı orchestrator
        üretiyor. Parametre imzada duruyor çünkü orchestrator `on_token=None`
        geçiyor."""
        async with Client(self._mcp_server_url) as client:
            catalog = await self._tool_catalog(client)
            plan = await self._plan(request, catalog)
            results = await self._run_plan(client, plan, request.user_id)

            # Profil-uygunluk bilgilendirmesi (bkz. modül docstring'i
            # "2026-08-28 eki") yalnızca `get_holdings` plandaysa anlamlı —
            # ucuz tool'u başka her plan için gereksiz yere ÇAĞIRMIYORUZ.
            risk_survey_score: int | None = None
            if any(name == "get_holdings" for name, _ in plan):
                risk_survey_score = await self._fetch_risk_survey_score(client, request.user_id)

        data: dict[str, Any] = {"selected_tools": [name for name, _ in plan]}
        failed: list[str] = []

        for name, _ in plan:
            payload, error = self._unwrap(results.get(name))
            if error is not None:
                logger.warning("[AJAN] portfolio: %s alinamadi — %s", name, error)
                failed.append(name)
                continue
            data[_RESULT_KEY[name]] = payload

        # Uydurma yok: anket hiç doldurulmamışsa (`risk_survey_score is None`)
        # ya da `get_holdings` başarısız olup "holdings" hiç eklenmediyse bu
        # kontrol sessizce ATLANIR — mevcut hacimli akış hiç etkilenmez.
        if "holdings" in data and risk_survey_score is not None:
            mismatch = _profil_uyum_disi_varliklar(data["holdings"], risk_survey_score)
            if mismatch:
                data["profil_uyum_disi_varliklar"] = mismatch
                # Bildirim ancak puanla YAN YANA anlamlı: "seviye 7" tek
                # başına kullanıcıya bir şey söylemez.
                data["anket_puani"] = risk_survey_score

        # Hiçbiri gelmediyse söylenecek bir şey yok. `base.error_response()`
        # yerine AgentResponse doğrudan kuruluyor: hangi tool'un seçilip hangi
        # sebeple düştüğü teşhis için `data` içinde kalmalı, ortak base.py'nin
        # error_response'u ise data taşımıyor (ve ortak dosyaya dokunmuyoruz).
        if failed and len(failed) == len(plan):
            first_error = next(
                (self._unwrap(results.get(name))[1] for name in failed), "Portföy verisi alınamadı"
            )
            return AgentResponse(
                agent_name=self.agent_name,
                success=False,
                summary_text="",
                data={"selected_tools": data["selected_tools"], "failed_tools": failed},
                error=first_error,
            )

        if failed:
            data["failed_tools"] = failed

        # Değer serisi anlatıya girmez: uzun sayı tablosu ücretli token ve
        # modelin yanlış değer okuma kaynağı. Grafik verisini dashboard
        # doğrudan API'den alıyor.
        performance = data.get("performance")
        if isinstance(performance, dict) and "series" in performance:
            # Seri atılırken DÖNEM BAŞLANGICI korunur. Özet skalerleri tarih
            # taşımıyor; seri de atılınca anlatıda hiçbir tarih kalmıyordu ve
            # cevap "son üç ayda +%5,43 kazandınız" deyip hangi üç ay olduğunu
            # söylemiyordu (ölçüldü, 1 Eylül 2026 — 21 Ağustos turundan beri
            # açık duran bulgu). Bitiş zaten `as_of`.
            seri = performance.get("series") or []
            data["performance"] = {
                **{k: v for k, v in performance.items() if k != "series"},
                "series_start": seri[0].get("date") if seri else None,
            }

        # Boş metinle "başarılı" dönmek yasak: orchestrator'ın merge adımı
        # `success=True` gördüğünde metni LLM'e anlatı için veriyor, metin boşsa
        # model de boş dönüyor ve kullanıcı bomboş bir baloncuk görüyor —
        # üstelik hiçbir yerde hata görünmüyor. Sessiz boşluk yerine açık hata.
        summary = _render(data)
        if not summary.strip():
            logger.warning("[AJAN] portfolio: veri toplandi ama ozet bos, plan=%s", plan)
            return AgentResponse(
                agent_name=self.agent_name,
                success=False,
                summary_text="",
                data=data,
                error="Portföy verisi alınamadı",
            )

        return AgentResponse(
            agent_name=self.agent_name,
            success=True,
            # Orchestrator'ın merge adımı bugün yalnızca summary_text okuyor
            # (agents/orchestrator.py::merge_responses); `data` hiçbir yerde
            # tüketilmiyor. LLM'e giden metin bu yüzden burada üretiliyor.
            # Cümle kurulmuyor — tool değerleri etiketlenip diziliyor.
            # TODO: merge `data`'yı okumaya geçince _render oraya taşınır.
            summary_text=summary,
            data=data,
        )

    # -- planlama ------------------------------------------------------------

    async def _tool_catalog(self, client: Client) -> str:
        """...

        Katalog okunamazsa boş dönülür: planlayıcı tool tanımadığı için boş
        plan üretir ve fallback devreye girer. Ajan çalışmaya devam eder —
        burada istisna kaçarsa orchestrator node'u ve tüm sohbet düşerdi.
        """
        global _catalog_cache
        if _catalog_cache is not None:
            return _catalog_cache

        try:
            tools = await client.list_tools()
        except Exception:
            logger.exception("[AJAN] portfolio: tool katalogu okunamadi")
            return ""

        entries: list[str] = []
        for tool in tools:
            if tool.name not in TOOLS:
                continue
            description = (tool.description or "").strip()
            schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None)
            entry = f"### {tool.name}\n{description}"
            if schema:
                entry += f"\nArgüman şeması: {json.dumps(schema, ensure_ascii=False)}"
            entries.append(entry)

        _catalog_cache = "\n\n".join(entries)
        return _catalog_cache

    async def _plan(self, request: AgentRequest, catalog: str) -> list[tuple[str, dict[str, Any]]]:
        history = request.context.get("recent_messages") or []
        prompt = _PLAN_PROMPT.format(
            # `settings.anchor_date` DEĞİL. O, sentetik verinin donmuş "bugün"ü
            # (şu an 1 Ağustos) ve yalnızca seed'i ilgilendiriyor. Buraya
            # yazıldığında model gerçekten o tarihte yaşadığını sanıyor: "bu ay",
            # "geçen hafta", "son 3 ay" gibi her göreli ifade yanlış pencereye
            # çevriliyordu. Kullanıcıya bugünün ne olduğunu söyleyen tek doğru
            # kaynak `turkey_today()`.
            today=turkey_today().isoformat(),
            tool_list=catalog,
            history=_format_history(history),
            query=request.query,
        )

        try:
            raw = await get_llm_client().generate(prompt)
        except Exception:
            logger.exception("[AJAN] portfolio: plan LLM cagrisi basarisiz, varsayilana dusuluyor")
            return list(_FALLBACK_PLAN)

        plan = _parse_plan(raw)
        if not plan:
            logger.warning(
                "[AJAN] portfolio: plan uretilemedi (%r), varsayilana dusuluyor", raw[:200]
            )
            return list(_FALLBACK_PLAN)

        logger.info("[AJAN] portfolio: sorgu=%r -> plan=%s", request.query[:60], plan)
        return plan

    async def _run_plan(
        self, client: Client, plan: list[tuple[str, dict[str, Any]]], user_id: str
    ) -> dict[str, dict[str, Any]]:
        """Plandaki tool'ları TEK oturumda ve eşzamanlı çağırır.

        `user_id` burada enjekte edilir; modelin ürettiği argümanlar arasında
        olsa bile ezilir. Modelin başka bir kullanıcının verisini istemesi
        mümkün olmamalı. Enjeksiyon YALNIZCA `_USER_SCOPED_TOOLS`'a yapılır:
        kullanıcıdan bağımsız tool'lar bu argümanı tanımıyor ve fastmcp
        tanımadığı argümanı doğrulama hatasıyla reddediyor.

        Zaman aşımı sunucu tarafında `@tool_handler` ile uygulanıyor; istemcide
        ikinci bir sınır koymak, sunucunun düzgün TIMEOUT zarfını göremeden
        bağlantıyı keserdi (docs/MCP-TOOLS.md §5).
        """

        async def _one(name: str, arguments: dict[str, Any]) -> tuple[str, dict[str, Any]]:
            if name in _USER_SCOPED_TOOLS:
                arguments = {**arguments, "user_id": user_id}
            try:
                result = await client.call_tool(name, arguments)
                return name, result.structured_content or {}
            except Exception:  # noqa: BLE001 - tek tool hatası ajanı düşürmesin
                logger.exception("[AJAN] portfolio: %s cagrisi basarisiz", name)
                return name, {
                    "success": False,
                    "error": {"code": "INTERNAL_ERROR", "message": _CLIENT_ERROR_MESSAGE},
                }

        pairs = await asyncio.gather(*(_one(name, args) for name, args in plan))
        return dict(pairs)

    async def _fetch_risk_survey_score(self, client: Client, user_id: str) -> int | None:
        """Profil-uygunluk kontrolü için GÜNCEL anket puanını ucuz bir MCP
        çağrısıyla okur (bkz. modül docstring'i "2026-08-28 eki") —
        `get_risk_assessment`'in aksine tam bir volatilite/VaR hesaplaması
        TETİKLEMEZ, tek satırlık bir okuma. `TOOLS`/`_USER_SCOPED_TOOLS`'a
        eklenmedi: bu, planlayıcının seçtiği bir tool değil, `get_holdings`
        seçildiğinde ajanın kendi kararıyla deterministik olarak çağırdığı
        yardımcı bir okuma.

        Hata durumunda (tool başarısız, bağlantı sorunu, anket hiç
        doldurulmamış) sessizce `None` döner — çağıran taraf bu durumda
        kontrolü ATLAR, hiçbir şey uydurmaz."""
        try:
            result = await client.call_tool("get_user_risk_survey", {"user_id": user_id})
        except Exception:  # noqa: BLE001 - bu çağrının hatası ana akışı düşürmesin
            logger.exception("[AJAN] portfolio: anket puani okunamadi")
            return None

        structured = result.structured_content or {}
        if not structured.get("success"):
            return None
        return structured.get("data", {}).get("risk_survey_score")

    @staticmethod
    def _unwrap(result: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str | None]:
        """Tool zarfını (veri, hata_mesajı) ikilisine ayırır."""
        if not isinstance(result, dict) or not result.get("success"):
            error = (result or {}).get("error") or {}
            return None, error.get("message") or "Portföy verisi alınamadı"
        payload = result.get("data")
        if not isinstance(payload, dict):
            return None, "Portföy verisi beklenen biçimde gelmedi"
        return payload, None


# ---------------------------------------------------------------------------
# Plan ayrıştırma
# ---------------------------------------------------------------------------


def _parse_plan(raw: str) -> list[tuple[str, dict[str, Any]]]:
    """LLM çıktısını (tool adı, argümanlar) listesine çevirir.

    Tanınmayan tool adı, sözlük olmayan argüman ve modelin yazdığı `user_id`
    sessizce elenir — model uydurduğunda ajan çökmemeli. Aynı tool iki kez
    seçilirse ilki alınır.
    """
    match = _JSON_ARRAY.search(raw or "")
    if match is None:
        return []
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []

    plan: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for item in parsed:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if name not in TOOLS or name in seen:
            continue
        arguments = item.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        # user_id modelden gelmez, ajan enjekte eder.
        arguments.pop("user_id", None)
        plan.append((name, arguments))
        seen.add(name)
        if len(plan) >= _MAX_TOOLS_PER_PLAN:
            break
    return plan


def _format_history(history: list[dict[str, str]]) -> str:
    if not history:
        return "(yok)"
    return "\n".join(
        f"{turn.get('role', '?')}: {turn.get('content', '')}" for turn in history[-_HISTORY_TURNS:]
    )


def _profil_uyum_disi_varliklar(
    holdings_data: dict[str, Any], risk_survey_score: int | None
) -> list[dict[str, Any]]:
    """Kullanıcının GÜNCEL elinde olan ama anket puanının artık izin
    vermediği VARLIKLARIN listesi — bkz. modül docstring'i "2026-08-31 eki",
    `advice_eligibility.mismatched_holdings`.

    2026-08-31: SINIF düzeyinden (`_profil_uyum_disi_siniflar`,
    `mismatched_asset_classes`) VARLIK düzeyine taşındı — sınıf, tek tek
    varlıkların uygunluğuna karar vermek için fazla kaba ve sınıfından
    ayrılan varlıklarda YANLIŞ bildiriyordu. Canlıda ölçüldü: Korumacı bir
    kullanıcının elindeki IOO (para piyasası fonu) için "Borçlanma Araçları
    artık tavsiye kapsamında değil" deniyordu — oysa sınıfı BOND (seviye 2)
    olsa da IOO'nun kendi uygunluk seviyesi 1'dir ve o kullanıcı için
    uyumludur.

    Saf bir fonksiyondur: kural `advice_eligibility`'nin, burada yalnızca
    `get_holdings` sonucunun şekli o fonksiyonun beklediği hâle çevriliyor.
    `risk_survey_score` `None` ise (anket hiç doldurulmamış) boş liste döner
    — uydurma yok.

    Dönen her kayıt sembol, sınıf ve varlığın uygunluk seviyesini taşır;
    bildirimin gerekçesi somut olabilsin diye (bkz. `_render`)."""
    if risk_survey_score is None:
        return []

    held: list[tuple[str, AssetClass]] = []
    for h in holdings_data.get("holdings", []):
        if h.get("price_missing"):
            continue
        sembol = h.get("symbol")
        sinif = h.get("asset_class")
        if sembol is None or sinif is None:
            continue
        try:
            held.append((sembol, AssetClass(sinif)))
        except ValueError:
            # Tanınmayan bir sınıf değeri (beklenmez, ama sessizce çökmektense
            # o varlığı atlamak zarif düşüştür).
            continue

    return [
        {"sembol": sembol, "sinif": sinif.value, "seviye": seviye}
        for sembol, sinif, seviye in sorted(
            mismatched_holdings(held, risk_survey_score), key=lambda kayit: kayit[0]
        )
    ]


# Nakit hareketleri de listeye giriyor (sembol süzgeci verilmediğinde), bu
# yüzden hepsinin Türkçe karşılığı burada olmalı — yoksa metne ham enum düşer.
_TX_TYPE_TR = {
    "buy": "alım",
    "sell": "satış",
    "dividend": "temettü",
    "interest": "faiz",
    "deposit": "para yatırma",
    "withdraw": "para çekme",
    "fee": "komisyon",
}


def _render(data: dict[str, Any]) -> str:
    """Tool verisini LLM'e verilecek kompakt metne çevirir.

    Bu bir anlatım değil serileştirmedir: cümle kurulmaz, yorum eklenmez,
    tool değerleri etiketlenip dizilir. JSON yerine düz `etiket: değer`
    satırları — aynı bilgi kabaca beşte bir token tutuyor ve model iç içe
    JSON'dan yanlış alan okumuyor.
    """
    blocks: list[str] = []

    summary = data.get("summary")
    if summary:
        gain = summary.get("total_gain_loss") or {}
        # "Yatırılan tutar" (net_invested), "toplam maliyet"in yerini alır:
        # kâr/zarar artık ona göre hesaplanıyor ve `değer - yatırılan = kâr`
        # özdeşliği tutuyor. Maliyet gösterilseydi üç rakam birbirini tutmaz,
        # aradaki fark (serbest nakit) açıklamasız kalırdı.
        # TARİH SAYININ YANINDA. Başlıkta da yazıyor ama merge adımı başlığı
        # düşürüyor: "Portföyünüzün toplam değeri 1.583.703,56 TL." cümlesinde
        # hiçbir tarih kalmıyordu (ölçüldü, 1 Eylül 2026, soru [1]) — oysa
        # fiyat yollarında tarih her satırda yazılı. Tarihsiz bir değer,
        # olmayan bir tazelik iddiasıdır.
        as_of = summary.get("as_of")
        toplam = f"Toplam değer: {_tr_amount(summary.get('total_value'))} TL"
        if as_of:
            toplam += f" ({_tr_date(as_of)} fiyatlarıyla)"
        lines = [f"Portföy özeti ({as_of or '—'})", toplam]
        # Her varlık kendi son fiyatıyla değerlenir; tarihler ayrışıyorsa özet
        # `as_of` ile olduğundan taze görünür. Fark varsa kullanıcıya söylenir
        # (CLAUDE.md §4 uydurmama).
        oldest = summary.get("oldest_price_date")
        if oldest and oldest != summary.get("as_of"):
            lines.append(f"En eski kullanılan fiyat tarihi: {oldest}")
        lines += [
            f"Yatırılan tutar: {_tr_amount(summary.get('net_invested'))} TL",
            f"Varlık maliyeti: {_tr_amount(summary.get('total_cost_basis'))} TL",
            f"Kâr/zarar: {_tr_amount(gain.get('amount'))} TL "
            f"({_tr_percent(gain.get('percent'), signed=True)})",
        ]
        # Nakit TUTAR olarak da yazılır. `allocation` onu yalnızca yüzde
        # dilimi olarak taşıyor; "ne kadar param nakitte duruyor" sorusu
        # tutar istiyor ve yüzdeyi toplam değerle çarpmak modelin yapması
        # yasak olan bir hesap. Ölçüldü (1 Eylül 2026): soru
        # "verilerde yer almıyor" cevabını alıyordu.
        lines.append(f"Serbest nakit: {_tr_amount(summary.get('cash_try'))} TL")
        allocation = summary.get("allocation") or []
        if allocation:
            parts = [
                f"{_ASSET_CLASS_TR.get(i['asset_class'], i['asset_class'])} %{_tr_amount(i['percent'])}"
                for i in allocation
            ]
            lines.append("Dağılım: " + " | ".join(parts))
        lines.append(f"Varlık sayısı: {summary.get('holdings_count', '—')}")
        blocks.append("\n".join(lines))

    holdings = data.get("holdings")
    if holdings:
        lines = ["Varlıklar"]
        for row in holdings.get("holdings") or []:
            if row.get("price_missing"):
                lines.append(f"{row['symbol']}: fiyat verisi yok, değer hesaplanamadı")
                continue
            lines.append(
                f"{row['symbol']} ({_ASSET_CLASS_TR.get(row.get('asset_class'), '—')}): "
                f"{_tr_amount(row.get('quantity'))} adet, "
                f"{_tr_amount(row.get('market_value_try'))} TL, "
                f"ağırlık %{_tr_amount(row.get('weight_percent'))}, "
                f"K/Z {_tr_percent(row.get('unrealized_pnl_percent'), signed=True)}"
            )
        # Satırların ağırlığı 100'e DEĞİL (100 − nakit%) değerine toplanır:
        # payda nakit dahil toplam değer. Nakit yazılmazsa aradaki fark
        # açıklanamaz kalıyor ve model eksik ağırlığı yorumlamaya çalışıyor.
        nakit = holdings.get("cash_try")
        if nakit is not None:
            lines.append(
                f"Serbest nakit (varlık değil, defter bakiyesi): "
                f"{_tr_amount(nakit)} TL, "
                f"ağırlık %{_tr_amount(holdings.get('cash_weight_percent'))}"
            )
        for label, key in (
            ("En çok kazandıran", "best_performer"),
            ("En çok kaybettiren", "worst_performer"),
        ):
            item = holdings.get(key)
            if item:
                lines.append(
                    f"{label}: {item['symbol']} "
                    f"{_tr_percent(item.get('unrealized_pnl_percent'), signed=True)}"
                )
        blocks.append("\n".join(lines))

    # bkz. modül docstring'i "2026-08-28 eki" — yalnızca GERÇEK bir uyumsuzluk
    # varsa eklenir (uydurulmuş bir "her şey uyumlu" bloğu YOK, boşsa hiç
    # bahsedilmez).
    mismatch = data.get("profil_uyum_disi_varliklar")
    if mismatch:
        # 2026-08-31: sınıf adı yerine VARLIK adı + kendi uygunluk seviyesi.
        # Sınıf düzeyi bildirim, sınıfından ayrılan varlıklarda yanlış
        # oluyordu (bkz. `_profil_uyum_disi_varliklar` docstring'i).
        puan = data.get("anket_puani")
        satirlar = [
            f"{kayit['sembol']} "
            f"({_ASSET_CLASS_TR.get(kayit['sinif'], kayit['sinif'])}, "
            f"uygunluk seviyesi {kayit['seviye']})"
            for kayit in mismatch
        ]
        puan_ifadesi = f" Anket puanınız {puan}." if puan is not None else ""
        blocks.append(
            "Risk profili uyumu\n"
            "Elinizde, güncel risk profilinize göre artık tavsiye kapsamında "
            "olmayan şu varlıklar var: "
            + ", ".join(satirlar)
            + "."
            + puan_ifadesi
            + " Bu bir satış zorunluluğu değildir, yalnızca bilgilendirmedir."
        )

    performans_payload = data.get("performance") or {}
    performance = performans_payload.get("summary")
    if performance:
        satirlar = ["Performans"]
        # DÖNEMİN TARİHLERİ HER ZAMAN YAZILIR. "Son üç ayda +%5,43 kazandınız"
        # cümlesi hangi üç ayı kastettiğini söylemeden eksiktir; aynı oturumda
        # farklı pencerelerden gelen iki yüzde karşılaştırılamaz hale gelir.
        baslangic = performans_payload.get("series_start")
        bitis = performans_payload.get("as_of")
        if baslangic and bitis:
            satir = f"Dönem: {_tr_date(baslangic)} – {_tr_date(bitis)}"
            if performans_payload.get("truncated_to_inception"):
                # Pencere portföyün ömründen uzunsa başlangıç ilk işleme
                # çekilir; "yıllık" yazıp dört aylık getiri göstermek kıyası
                # olduğundan iyi ya da kötü gösterir.
                satir += " (portföy bu dönemden genç, başlangıç ilk işleme çekildi)"
            satirlar.append(satir)
        satirlar += [
            f"Dönem değişimi: {_tr_percent(performance.get('change_percent'), signed=True)} "
            f"({_tr_amount(performance.get('change_amount'))} TL)",
            f"Dönem başı: {_tr_amount(performance.get('start_value'))} TL · "
            f"dönem sonu: {_tr_amount(performance.get('end_value'))} TL",
        ]
        blocks.append("\n".join(satirlar))

    transactions = data.get("transactions")
    if transactions:
        blocks.append(_render_transactions(transactions))

    benchmark = data.get("benchmark")
    if benchmark:
        parts = [f"Portföy {_tr_percent(benchmark.get('portfolio_return_percent'), signed=True)}"]
        parts += [
            f"{b['name']} {_tr_percent(b.get('return_percent'), signed=True)}"
            for b in benchmark.get("benchmarks") or []
        ]
        # Kıyaslamanın da dönemi yazılır: aynı sayfadaki iki yüzde ancak aynı
        # dönemi kapsıyorsa karşılaştırılabilir.
        baslik = "Kıyaslama"
        if benchmark.get("start_date") and benchmark.get("end_date"):
            baslik += f" ({_tr_date(benchmark['start_date'])} – {_tr_date(benchmark['end_date'])})"
        blocks.append(f"{baslik}: " + " | ".join(parts))

    price_history = data.get("price_history")
    if price_history:
        blocks.append(_render_price_history(price_history))

    if data.get("failed_tools"):
        blocks.append("Alınamayan bilgiler: " + ", ".join(data["failed_tools"]))

    return "\n\n".join(blocks) if blocks else "Portföy verisi bulunamadı."


def _render_price_history(payload: dict[str, Any]) -> str:
    """Fiyat serisini UÇ NOKTALARA indirger: başlangıç, bitiş, değişim.

    Tam seri (60-120 nokta) anlatıya girmez — hem ücretli token hem de modelin
    yanlış değer okuma kaynağı. Grafik zaten seriyi API'den kendisi alıyor.
    Sayısal değişim burada hesaplanıyor; LLM'in seriden yüzde çıkarması
    istenmiyor.

    Bulunamayan semboller SÖYLENİR: sessizce atlanırsa kullanıcı sorduğu
    varlığın cevapta olmadığını fark etmez (uydurmama, AK 5.5).
    """
    series = payload.get("series") or {}
    satirlar: list[str] = []

    for sembol, noktalar in sorted(series.items()):
        if not noktalar:
            continue
        ilk = noktalar[0]
        son = noktalar[-1]
        ilk_fiyat = float(ilk.get("close") or 0)
        son_fiyat = float(son.get("close") or 0)
        degisim = ((son_fiyat / ilk_fiyat - 1) * 100) if ilk_fiyat else None
        satirlar.append(
            f"{sembol}: {ilk.get('date')} {_tr_amount(ilk_fiyat)} → "
            f"{son.get('date')} {_tr_amount(son_fiyat)}"
            + (f" ({_tr_percent(degisim, signed=True)})" if degisim is not None else "")
        )

    eksik = list(payload.get("unknown_symbols") or []) + list(
        payload.get("symbols_without_data") or []
    )
    if eksik:
        satirlar.append("Veri bulunamayan semboller: " + ", ".join(eksik))

    if not satirlar:
        return "Fiyat geçmişi: istenen sembol(ler) için veri yok."
    return f"Fiyat geçmişi ({payload.get('window', '—')})\n" + "\n".join(satirlar)


def _render_transactions(payload: dict[str, Any]) -> str:
    """İşlemleri sembol ve tür bazında toplulaştırır, KRONOLOJİYİ KORUYARAK.

    Ham liste 50 satır olabiliyor; anlatı için gereken "ne kadar aldım/sattım"
    bilgisi birkaç satıra sığıyor. Tam liste `data` içinde duruyor, grafikteki
    işaretçiler onu kullanıyor.

    NEDEN TARİH VAR. İlk sürüm yalnızca toplamları veriyordu ve tarihleri
    atıyordu; "ilk hangisini almışım", "en son ne zaman altın aldım", "önce mi
    sonra mı" gibi sorular cevapsız kalıyordu — model elinde tarih olmadığı
    için özeti döküp geçiyordu. Token tasarrufu doğruydu, kronolojiyi tamamen
    yok etmek yanlıştı. Her kova artık ilk ve son işlem gününü taşıyor ve
    kovalar İLK İŞLEM TARİHİNE göre sıralanıyor: "ilk" sorusunun cevabı
    listenin ilk satırı.
    """
    rows = payload.get("transactions") or []
    if not rows:
        return "İşlemler: seçilen aralıkta işlem yok."

    totals: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row.get("symbol") or "NAKİT", row.get("type") or "?")
        gun = str(row.get("transaction_date") or "")[:10]
        bucket = totals.get(key)
        if bucket is None:
            bucket = {"count": 0, "amount": 0.0, "quantity": 0.0, "ilk": gun, "son": gun}
            totals[key] = bucket
        bucket["count"] += 1
        bucket["amount"] += abs(float(row.get("cash_amount_try") or 0))
        bucket["quantity"] += float(row.get("quantity") or 0)
        # Servis eskiden yeniye sıralı döndürüyor; yine de sıralamaya
        # güvenmeden min/max alınıyor (filtre ya da kaynak değişebilir).
        if gun and (not bucket["ilk"] or gun < bucket["ilk"]):
            bucket["ilk"] = gun
        if gun and (not bucket["son"] or gun > bucket["son"]):
            bucket["son"] = gun

    # Sıralama ilk işlem tarihine göre: en eski hareket en üstte.
    sirali = sorted(totals.items(), key=lambda kv: (kv[1]["ilk"], kv[0]))

    parts = []
    for (symbol, tx_type), bucket in sirali:
        # ADET YALNIZCA ANLAMLIYSA YAZILIR. Nakit ayaklarında (para yatırma,
        # çekme, faiz) "adet" diye bir kavram yok ve satır "1 para yatırma,
        # 0,00 adet, toplam 1.250.000,00 TL" gibi çıkıyordu — sıfır bir ÖLÇÜM
        # değil, o alanın o işlem için tanımsız olduğunun işareti (ölçüldü,
        # 1 Eylül 2026).
        satir = f"{symbol} {bucket['count']} {_TX_TYPE_TR.get(tx_type, tx_type)}, "
        if bucket["quantity"]:
            satir += f"{_tr_amount(bucket['quantity'])} adet, "
        satir += f"toplam {_tr_amount(bucket['amount'])} TL, ilk {_tr_date(bucket['ilk'])}"
        if bucket["son"] != bucket["ilk"]:
            satir += f", son {_tr_date(bucket['son'])}"
        parts.append(satir)

    # Toplam sayı AYRICA yazılır.
    #
    # "Bu ay KAÇ işlem yaptım?" sorusuna sembol bazlı bir döküm dönüyor ama
    # sorulan sayı hiçbir yerde geçmiyordu; toplamı satırlardan saymak
    # merge adımına kalıyordu ve o da yapmıyordu (ölçüldü, 23 Ağustos test
    # turu). Sayı burada, veriden hesaplanıyor — LLM'in sayması istenmiyor.
    baslik = f"İşlemler ({len(rows)} işlem, eskiden yeniye sıralı)"
    return baslik + "\n" + "\n".join(parts)
