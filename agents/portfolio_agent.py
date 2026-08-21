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
from app.core.config import settings
from app.core.llm_client import get_llm_client

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
)

# Tool sonucunun `data` içinde duracağı anahtar.
_RESULT_KEY = {
    "get_portfolio_summary": "summary",
    "get_holdings": "holdings",
    "get_portfolio_performance": "performance",
    "get_transactions": "transactions",
    "get_benchmark_comparison": "benchmark",
}

# Plan başına tavan: modelin "ne olur ne olmaz hepsini çağırayım" davranışını
# engeller. Her tool ücretli token ve bir DB sorgusu demek.
_MAX_TOOLS_PER_PLAN = 3

# Plan üretilemezse veya hiçbiri geçerli değilse: en ucuz ve en genel tool.
_FALLBACK_PLAN = [("get_portfolio_summary", {})]

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

        data: dict[str, Any] = {"selected_tools": [name for name, _ in plan]}
        failed: list[str] = []

        for name, _ in plan:
            payload, error = self._unwrap(results.get(name))
            if error is not None:
                logger.warning("[AJAN] portfolio: %s alinamadi — %s", name, error)
                failed.append(name)
                continue
            data[_RESULT_KEY[name]] = payload

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
            data["performance"] = {k: v for k, v in performance.items() if k != "series"}

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
            today=settings.anchor_date.isoformat(),
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
        mümkün olmamalı.

        Zaman aşımı sunucu tarafında `@tool_handler` ile uygulanıyor; istemcide
        ikinci bir sınır koymak, sunucunun düzgün TIMEOUT zarfını göremeden
        bağlantıyı keserdi (docs/MCP-TOOLS.md §5).
        """

        async def _one(name: str, arguments: dict[str, Any]) -> tuple[str, dict[str, Any]]:
            try:
                result = await client.call_tool(name, {**arguments, "user_id": user_id})
                return name, result.structured_content or {}
            except Exception as exc:  # noqa: BLE001 - tek tool hatası ajanı düşürmesin
                logger.exception("[AJAN] portfolio: %s cagrisi basarisiz", name)
                return name, {
                    "success": False,
                    "error": {"code": "INTERNAL_ERROR", "message": str(exc)},
                }

        pairs = await asyncio.gather(*(_one(name, args) for name, args in plan))
        return dict(pairs)

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


_ASSET_CLASS_TR = {
    "stock": "Hisse Senedi",
    "precious_metal": "Kıymetli Maden",
    "currency": "Döviz",
    "bond": "Tahvil",
    "cash": "Nakit",
}

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


def _tr_amount(value: Any, *, signed: bool = False) -> str:
    if value is None:
        return "—"
    text = f"{float(value):+,.2f}" if signed else f"{float(value):,.2f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _tr_percent(value: Any, *, signed: bool = False) -> str:
    if value is None:
        return "—"
    text = f"{float(value):+.2f}" if signed else f"{float(value):.2f}"
    return text.replace(".", ",") + "%"


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
        lines = [
            f"Portföy özeti ({summary.get('as_of', '—')})",
            f"Toplam değer: {_tr_amount(summary.get('total_value'))} TL",
        ]
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

    performance = (data.get("performance") or {}).get("summary")
    if performance:
        blocks.append(
            "Performans\n"
            f"Dönem değişimi: {_tr_percent(performance.get('change_percent'), signed=True)} "
            f"({_tr_amount(performance.get('change_amount'))} TL)\n"
            f"Dönem başı: {_tr_amount(performance.get('start_value'))} TL · "
            f"dönem sonu: {_tr_amount(performance.get('end_value'))} TL"
        )

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
        blocks.append("Kıyaslama: " + " | ".join(parts))

    if data.get("failed_tools"):
        blocks.append("Alınamayan bilgiler: " + ", ".join(data["failed_tools"]))

    return "\n\n".join(blocks) if blocks else "Portföy verisi bulunamadı."


def _render_transactions(payload: dict[str, Any]) -> str:
    """İşlemleri sembol ve tür bazında toplulaştırır.

    Ham liste 50 satır olabiliyor; anlatı için gereken "ne kadar aldım/sattım"
    bilgisi birkaç satıra sığıyor. Tam liste `data` içinde duruyor, grafikteki
    işaretçiler onu kullanıyor.
    """
    rows = payload.get("transactions") or []
    if not rows:
        return "İşlemler: seçilen aralıkta işlem yok."

    totals: dict[tuple[str, str], dict[str, float]] = {}
    for row in rows:
        key = (row.get("symbol") or "NAKİT", row.get("type") or "?")
        bucket = totals.setdefault(key, {"count": 0, "amount": 0.0, "quantity": 0.0})
        bucket["count"] += 1
        bucket["amount"] += abs(float(row.get("cash_amount_try") or 0))
        bucket["quantity"] += float(row.get("quantity") or 0)

    parts = [
        f"{symbol} {bucket['count']} {_TX_TYPE_TR.get(tx_type, tx_type)}, "
        f"{_tr_amount(bucket['quantity'])} adet, toplam {_tr_amount(bucket['amount'])} TL"
        for (symbol, tx_type), bucket in sorted(totals.items())
    ]
    return "İşlemler\n" + "\n".join(parts)
