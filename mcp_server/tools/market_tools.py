"""search_market_news MCP tool'u. Piyasa Araştırma Ajanı'nın finansal haber ve
raporlara eriştiği tek kapı.

Mimari kural: ajanlar veriye doğrudan erişmez. Bu yüzden `rag/retriever.py`
doğrudan ajandan değil, buradan çağrılır — böylece yetkilendirme, loglama ve
zaman aşımı politikası ileride tek noktada uygulanabilir.

Saf DB tabanlı RAG: LLM yanıt üretmez, internetten canlı veri çekmez. Tool ham
doküman parçalarını döndürür ("tool veri döner, ajan yorumlar" ilkesi);
veritabanında yeterince alakalı bir sonuç yoksa `found: false` ile birlikte
bulunamadı mesajı döner.
"""

import logging
from typing import Any

from fastmcp import FastMCP

logger = logging.getLogger(__name__)

# Chroma bağlantısı ve embedding modeli ilk kullanımda bir kez kurulur ve süreç
# boyunca bellekte kalır. Her istekte yeniden oluşturulursa her soru birkaç
# saniye ek gecikme demek.
_retriever = None


def _get_retriever():
    global _retriever
    if _retriever is None:
        from rag.retriever import Retriever

        logger.info("RAG retriever hazırlanıyor (embedding modeli + Chroma bağlantısı)...")
        _retriever = Retriever()
        logger.info("RAG retriever hazır.")
    return _retriever


def register(mcp: FastMCP) -> None:
    @mcp.tool(name="search_market_news")
    async def search_market_news(query: str, top_k: int = 5) -> dict[str, Any]:
        """Finansal haber, bilanço ve analiz dokümanlarında vektör tabanlı
        arama yapar. Veritabanında sorguyla yeterince alakalı bir kayıt yoksa
        `found: false` döner — sonuç uydurulmaz, dış kaynaktan da çekilmez.

        Args:
            query: Kullanıcının piyasa/haber sorusu.
            top_k: Getirilecek en fazla doküman parçası sayısı.

        Returns:
            Başarılıysa {"success": true, "data": {"found": bool, "message": str | None,
            "results": [{"content": ..., "metadata": ..., "distance": ...}, ...]}}.
            Hata durumunda {"success": false, "error": {"code": ..., "message": ...}}.
        """
        try:
            retriever = _get_retriever()
            result = retriever.answer(query, top_k=top_k)
            return {"success": True, "data": result}
        except Exception as exc:  # noqa: BLE001 - tool sınırında hata sızdırılmaz
            logger.exception("RAG sorgusu başarısız")
            return {
                "success": False,
                "error": {"code": "RAG_ERROR", "message": str(exc)},
            }
