"""search_market_news MCP tool'u. Piyasa Araştırma Ajanı'nın finansal haber ve
raporlara eriştiği tek kapı.

Mimari kural: ajanlar veriye doğrudan erişmez. Bu yüzden `rag/pipeline.py`
doğrudan ajandan değil, buradan çağrılır — böylece yetkilendirme, loglama ve
zaman aşımı politikası ileride tek noktada uygulanabilir.

Not: `FinancialRAGAssistant` getirme (retrieval) ve yanıt üretimini birlikte
yapıyor, bu yüzden tool ham doküman yerine üretilmiş metni döndürüyor. Portföy
tool'undaki "tool veri döner, ajan yorumlar" ayrımı burada tam sağlanamıyor;
pipeline ikiye ayrılırsa düzeltilmeli (TODO).
"""

import logging
from typing import Any

from fastmcp import FastMCP

logger = logging.getLogger(__name__)

# Embedding modeli ve Chroma indeksi ilk kullanımda bir kez yüklenir ve süreç
# boyunca bellekte kalır. Her istekte yeniden oluşturulursa her soru 10-20
# saniye ek gecikme demek.
_assistant = None


def _get_assistant():
    global _assistant
    if _assistant is None:
        from rag.pipeline import FinancialRAGAssistant

        logger.info("RAG asistanı yükleniyor (embedding modeli + Chroma indeksi)...")
        _assistant = FinancialRAGAssistant()
        logger.info("RAG asistanı hazır.")
    return _assistant


def register(mcp: FastMCP) -> None:
    @mcp.tool(name="search_market_news")
    async def search_market_news(query: str, session_id: str = "default") -> dict[str, Any]:
        """Finansal haber, bilanço ve analiz dokümanlarında hibrit arama
        (vektör + anahtar kelime) yapar ve bulunan kaynaklara dayalı bir yanıt
        üretir. Yanıt yalnızca dokümanlardaki bilgiye dayanır.

        Args:
            query: Kullanıcının piyasa/haber sorusu.
            session_id: Çok turlu sohbette bağlamı korumak için oturum kimliği.

        Returns:
            Başarılıysa {"success": true, "data": {"answer": "..."}}.
            Hata durumunda {"success": false, "error": {"code": ..., "message": ...}}.
        """
        try:
            assistant = _get_assistant()
            answer = await assistant.chat_async(query, session_id=session_id)
            return {"success": True, "data": {"answer": answer}}
        except FileNotFoundError as exc:
            logger.exception("RAG yapılandırma dosyası bulunamadı")
            return {
                "success": False,
                "error": {"code": "RAG_CONFIG_MISSING", "message": str(exc)},
            }
        except Exception as exc:  # noqa: BLE001 - tool sınırında hata sızdırılmaz
            logger.exception("RAG sorgusu başarısız")
            return {
                "success": False,
                "error": {"code": "RAG_ERROR", "message": str(exc)},
            }
