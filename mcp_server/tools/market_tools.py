"""search_market_news MCP tool'u. Piyasa Araştırma Ajanı'nın finansal haber ve
rapor dokümanlarına eriştiği tek kapı.

Mimari kural: ajanlar veriye doğrudan erişmez. Bu yüzden `rag/retriever.py`
doğrudan ajandan değil, buradan çağrılır — yetkilendirme, loglama ve zaman
aşımı politikası tek noktada uygulanabilsin diye.

Saf DB tabanlı RAG: LLM yanıt üretmez, internetten canlı veri çekmez —
yalnızca `data/documents/`'dan `rag.ingest` ile Chroma'ya işlenmiş dokümanları
arar ve ham parçaları döndürür. Bu, `docs/MCP-TOOLS.md`'nin §10'daki "RAG
getirme/üretim ayrımı yok" notunu kapatır.
"""

import logging
from typing import Any

import anyio.to_thread
from app.core.config import settings
from fastmcp import FastMCP

from mcp_server.tools._base import ToolErrorCode, ToolFailure, tool_handler
from rag.retriever import NOT_FOUND_MESSAGE, Retriever

logger = logging.getLogger(__name__)

# Embedding modeli ve Chroma bağlantısı ilk kullanımda bir kez kurulur ve süreç
# boyunca bellekte kalır. Her istekte yeniden oluşturulursa her soru birkaç
# saniye ek gecikme demek.
_retriever: Retriever | None = None


def _get_retriever() -> Retriever:
    """Bloklayan yükleme (embedding modeli + Chroma bağlantısı). ASLA olay
    döngüsünden doğrudan çağrılmaz; çağıran taraf thread'e alır — aksi hâlde
    ilk piyasa sorusu boyunca tüm süreç (diğer kullanıcıların SSE akışları
    dahil) donar."""
    global _retriever
    if _retriever is None:
        logger.info(
            "RAG retriever hazırlanıyor (embedding modeli + Chroma bağlantısı)..."
        )
        _retriever = Retriever()
        logger.info("RAG retriever hazır.")
    return _retriever


def register(mcp: FastMCP) -> list[str]:
    @mcp.tool(name="search_market_news")
    @tool_handler(timeout=settings.mcp_tool_timeout_rag)
    async def search_market_news(query: str, top_k: int = 5) -> dict[str, Any]:
        """Finansal haber, bilanço ve analiz dokümanlarında vektör + anahtar
        kelime tabanlı hibrit arama yapar. Yanıt LLM tarafından üretilmez,
        internetten de çekilmez — yalnızca veritabanındaki dokümanlar aranır.

        Ne zaman kullanılır: piyasa gelişmeleri, şirket bilançoları, faiz ve
        enflasyon haberleri, "X şirketinin son çeyreği nasıldı" gibi dış dünyaya
        ait sorular.

        Ne zaman kullanılmaz: kullanıcının kendi portföyüne ait sorular
        (get_portfolio_summary), kendi riskine ait sorular
        (get_risk_assessment).

        Args:
            query: Kullanıcının piyasa/haber sorusu (Türkçe, serbest metin).
            top_k: Getirilecek en fazla doküman parçası sayısı.

        Returns:
            Başarılı: {"success": true, "data": {"results": [{"content": "...",
            "metadata": {...}, "distance": 0.0}, ...]}}.
            Hata: {"success": false, "error": {"code": "NOT_FOUND", "message":
            "..."}} — veritabanında sorguyla yeterince alakalı bir kayıt yoksa.
        """
        retriever = await anyio.to_thread.run_sync(_get_retriever)
        results = await anyio.to_thread.run_sync(retriever.retrieve, query, top_k)

        if not results:
            raise ToolFailure(ToolErrorCode.NOT_FOUND, NOT_FOUND_MESSAGE)

        return {"results": results}

    return ["search_market_news"]
