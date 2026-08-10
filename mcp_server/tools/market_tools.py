"""TODO: Piyasa Araştırma Ajanı için RAG tabanlı tool. rag/retriever.py hazır olunca uygulanacak."""

from typing import Any

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool(name="search_market_news")
    def search_market_news(query: str, top_k: int = 5) -> dict[str, Any]:
        """Finansal haber ve raporlarda RAG ile arama yapar.

        Args:
            query: Arama sorgusu.
            top_k: Döndürülecek en alakalı sonuç sayısı.
        """
        raise NotImplementedError("TODO: Piyasa Araştırma Ajanı / RAG henüz uygulanmadı")
