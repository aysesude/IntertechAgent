"""search_market_news MCP tool'u. Piyasa Araştırma Ajanı'nın finansal haber ve
raporlara eriştiği tek kapı.

Mimari kural: ajanlar veriye doğrudan erişmez. Bu yüzden `rag/pipeline.py`
doğrudan ajandan değil, buradan çağrılır — yetkilendirme, loglama ve zaman
aşımı politikası tek noktada uygulanabilsin diye.

Not: `FinancialRAGAssistant` getirme (retrieval) ve yanıt üretimini birlikte
yapıyor, bu yüzden tool ham doküman yerine üretilmiş metni döndürüyor. Portföy
tool'undaki "tool veri döner, ajan yorumlar" ayrımı burada tam sağlanamıyor;
pipeline ikiye ayrılırsa düzeltilmeli (TODO — ayrı görev).
"""

import logging
from typing import Any

import anyio.to_thread
from fastmcp import FastMCP

from app.core.config import settings
from mcp_server.tools._base import ToolErrorCode, ToolFailure, tool_handler

logger = logging.getLogger(__name__)

# Embedding modeli ve Chroma indeksi ilk kullanımda bir kez yüklenir ve süreç
# boyunca bellekte kalır. Her istekte yeniden oluşturulursa her soru 10-20
# saniye ek gecikme demek.
_assistant = None


def _get_assistant():
    """Bloklayan yükleme (10-20 sn). ASLA olay döngüsünden doğrudan çağrılmaz;
    çağıran taraf thread'e alır — aksi hâlde ilk piyasa sorusu boyunca tüm
    süreç (diğer kullanıcıların SSE akışları dahil) donar."""
    global _assistant
    if _assistant is None:
        from rag.pipeline import FinancialRAGAssistant

        logger.info("RAG asistanı yükleniyor (embedding modeli + Chroma indeksi)...")
        _assistant = FinancialRAGAssistant()
        logger.info("RAG asistanı hazır.")
    return _assistant


def register(mcp: FastMCP) -> list[str]:
    @mcp.tool(name="search_market_news")
    @tool_handler(timeout=settings.mcp_tool_timeout_rag)
    async def search_market_news(query: str, session_id: str = "default") -> dict[str, Any]:
        """Finansal haber, bilanço ve analiz dokümanlarında hibrit arama
        (vektör + anahtar kelime) yapıp bulunan kaynaklara dayalı bir yanıt
        üretir. Yanıt yalnızca dokümanlardaki bilgiye dayanır.

        Ne zaman kullanılır: piyasa gelişmeleri, şirket bilançoları, faiz ve
        enflasyon haberleri, "X şirketinin son çeyreği nasıldı" gibi dış dünyaya
        ait sorular.

        Ne zaman kullanılmaz: kullanıcının kendi portföyüne ait sorular
        (get_portfolio_summary), kendi riskine ait sorular
        (get_risk_assessment), güncel fiyat sorgusu (get_market_snapshot).

        Args:
            query: Kullanıcının piyasa/haber sorusu (Türkçe, serbest metin).
            session_id: Çok turlu sohbette bağlamı korumak için oturum kimliği.

        Returns:
            Başarılı: {"success": true, "data": {"answer": "...dokümanlara
            dayalı Türkçe yanıt..."}}.
            Hata: {"success": false, "error": {"code": "PROVIDER_UNAVAILABLE" |
            "TIMEOUT" | "INTERNAL_ERROR", "message": "..."}} — RAG indeksi ya da
            LLM erişilemezse.
        """
        try:
            # Yükleme bloklayıcı ve senkron; thread'e alınır.
            assistant = await anyio.to_thread.run_sync(_get_assistant)
        except FileNotFoundError as exc:
            raise ToolFailure(
                ToolErrorCode.PROVIDER_UNAVAILABLE,
                "Haber ve doküman arşivine şu anda ulaşılamıyor.",
                detail=f"RAG yapılandırma/indeks dosyası bulunamadı: {exc}",
            ) from exc

        answer = await assistant.chat_async(query, session_id=session_id)
        return {"answer": answer}

    return ["search_market_news"]
