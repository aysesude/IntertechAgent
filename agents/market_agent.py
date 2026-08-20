"""Piyasa Araştırma Ajanı: `search_market_news` MCP tool'unu çağırır, dönen
doküman parçalarını LLM ile doğal dile döker ve altına kaynak listesi ekler.

RAG vektör deposuna doğrudan erişmez — tüm veri erişimi MCP Server üzerinden
geçer. Tool saf DB tabanlı RAG'dır (LLM yok, canlı internet yok); LLM yalnızca
bu ajanda, yalnızca tool'dan gelen metni yeniden ifade etmek için devreye girer.
Sayısal hiçbir değer LLM tarafından üretilmez.

İki savunma katmanı var:
  1. Deterministik filtre — sorgudaki şirket/dönem tespit edilip tool'a
     geçirilir, arama uzayı benzerlik hesaplanmadan önce daralır.
  2. Etiketli parçalar — her parça `[n] Başlık (Kaynak, tarih)` başlığıyla
     LLM'e verilir. Eskiden parçalar etiketsiz birleştiriliyordu; model iki
     ayrı şirketin rakamlarını tek cümlede harmanlayabiliyordu.
"""

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from agents.base import AgentRequest, AgentResponse, BaseAgent
from agents.market_query import filtre_cikar
from app.core.llm_client import get_llm_client

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "market_agent.md").read_text(
    encoding="utf-8"
)

_KAYNAK_BASLIGI = "\n\nKaynaklar:\n"


def _tarih_bicimle(ham: Any) -> str:
    """`2026-07-28` → `28.07.2026`. Ayrıştırılamayan değer olduğu gibi döner —
    tarih biçimi yüzünden cevabın tamamını kaybetmek istemiyoruz."""
    metin = str(ham or "").strip()
    try:
        return date.fromisoformat(metin[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return metin


def _parca_etiketi(metadata: dict[str, Any]) -> str:
    """`ASELSAN 2026 2. Çeyrek Finansal Sonuçları (KAP, 28.07.2026)`"""
    baslik = str(metadata.get("baslik") or metadata.get("dosya") or "Başlıksız belge")
    parcalar = [str(metadata.get(alan)) for alan in ("kaynak", "tarih") if metadata.get(alan)]
    if not parcalar:
        return baslik
    if metadata.get("tarih"):
        parcalar[-1] = _tarih_bicimle(metadata["tarih"])
    return f"{baslik} ({', '.join(parcalar)})"


def _dokuman_blogu(results: list[dict[str, Any]]) -> str:
    """LLM'e verilecek metin. Numaralandırma ve kaynak başlığı, modelin iki
    farklı belgeyi tek bir anlatıya karıştırmasını zorlaştırır."""
    return "\n\n".join(
        f"[{i}] {_parca_etiketi(r.get('metadata') or {})}\n{r.get('content', '')}"
        for i, r in enumerate(results, start=1)
    )


def _kaynak_blogu(results: list[dict[str, Any]]) -> str:
    """Kullanıcıya gösterilecek kaynak listesi. Aynı belgeden birden çok parça
    gelebilir; tekrar edenler ilk görülme sırası korunarak teklenir."""
    gorulen: list[str] = []
    for r in results:
        etiket = _parca_etiketi(r.get("metadata") or {})
        if etiket not in gorulen:
            gorulen.append(etiket)
    if not gorulen:
        return ""
    return _KAYNAK_BASLIGI + "\n".join(f"- {etiket}" for etiket in gorulen)


class MarketAgent(BaseAgent):
    agent_name = "market_agent"

    async def execute(
        self, request: AgentRequest, *, on_token: Callable[[str], None] | None = None
    ) -> AgentResponse:
        filtreler = filtre_cikar(request.query)
        tool_result = await self.call_mcp_tool(
            "search_market_news", {"query": request.query, **filtreler}
        )

        # Yedek deneme: filtre tespiti yanılmış olabilir (ör. sorguda geçen
        # şirket adı belgelerde farklı kodla etiketlenmiştir). Filtreli arama
        # boş dönerse bir kez de filtresiz denenir — filtre bir hızlandırma ve
        # doğruluk aracıdır, cevabı büsbütün engellememeli.
        if not tool_result.get("success") and filtreler:
            tool_result = await self.call_mcp_tool(
                "search_market_news", {"query": request.query}
            )

        if not tool_result.get("success"):
            error = tool_result.get("error", {})
            return self.error_response(error.get("message", "Piyasa verisi alınamadı"))

        data = tool_result["data"]
        results = data.get("results") or []
        summary_text = await self._summarize(request.query, results, on_token=on_token)

        return AgentResponse(
            agent_name=self.agent_name,
            success=True,
            summary_text=summary_text,
            data=data,
        )

    async def _summarize(
        self,
        query: str,
        results: list[dict[str, Any]],
        *,
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        prompt = _PROMPT_TEMPLATE.format(query=query, documents=_dokuman_blogu(results))

        llm = get_llm_client()
        full_text = ""
        async for chunk in llm.stream(prompt):
            full_text += chunk
            if on_token is not None:
                on_token(chunk)

        # Kaynak listesi LLM'e bırakılmaz (uydurulmuş kaynak riski) — metadata'dan
        # üretilip akışın sonuna eklenir, kullanıcı da akarken görsün diye
        # on_token'dan geçirilir.
        kaynaklar = _kaynak_blogu(results)
        if kaynaklar:
            full_text += kaynaklar
            if on_token is not None:
                on_token(kaynaklar)

        return full_text
