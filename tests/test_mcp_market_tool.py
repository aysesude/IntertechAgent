import pytest
from fastmcp import Client, FastMCP

from mcp_server.tools import market_tools
from mcp_server.tools._base import DEFAULT_MESSAGES, ToolErrorCode


@pytest.fixture()
def mcp_server():
    mcp = FastMCP("test-finans-mcp")
    market_tools.register(mcp)
    return mcp


class _FakeRetriever:
    """rag.retriever.Retriever'in yerine gecer: gercek Chroma/embedding modeli
    olmadan tool'un zarf/hata davranisini test eder."""

    def __init__(self, results: list[dict]) -> None:
        self._results = results

    def retrieve(self, query: str, top_k: int) -> list[dict]:
        return self._results


async def test_search_market_news_tool_success(mcp_server, monkeypatch):
    fake_results = [
        {
            "content": "Örnek Şirket net kârı 2,4 milyar TL oldu.",
            "metadata": {"baslik": "Örnek Şirket 2026 2. Çeyrek Finansal Sonuçları"},
            "distance": 0.2,
        }
    ]
    monkeypatch.setattr(
        market_tools, "_get_retriever", lambda: _FakeRetriever(fake_results)
    )

    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "search_market_news", {"query": "Örnek Şirket net kârı ne kadar"}
        )

    envelope = result.structured_content
    assert envelope["success"] is True
    assert envelope["data"]["results"] == fake_results


async def test_search_market_news_tool_not_found(mcp_server, monkeypatch):
    # Bos sonuc: veritabaninda alakali bir kayit yok. Uydurma yok — tool
    # standart NOT_FOUND doner (AK 5.5, 5.10).
    monkeypatch.setattr(market_tools, "_get_retriever", lambda: _FakeRetriever([]))

    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "search_market_news", {"query": "Bitcoin fiyatı ne kadar"}
        )

    envelope = result.structured_content
    assert envelope["success"] is False
    assert envelope["error"]["code"] == ToolErrorCode.NOT_FOUND.value
    assert (
        envelope["error"]["message"] != DEFAULT_MESSAGES[ToolErrorCode.NOT_FOUND]
    )  # ozellesmis mesaj


async def test_search_market_news_tool_beklenmeyen_hatada_cokmez(
    mcp_server, monkeypatch
):
    """Chroma'ya baglanti kurulamazsa (server ayakta degil, embedding modeli
    yuklenemedi vb.) tool zarf doner, teknik detay kullaniciya sizmaz."""

    def patlat():
        raise RuntimeError("connection refused at http://chroma:8000")

    monkeypatch.setattr(market_tools, "_get_retriever", patlat)

    async with Client(mcp_server) as client:
        result = await client.call_tool(
            "search_market_news", {"query": "herhangi bir soru"}
        )

    envelope = result.structured_content
    assert envelope["success"] is False
    assert envelope["error"]["code"] == ToolErrorCode.INTERNAL_ERROR.value
    assert "chroma" not in envelope["error"]["message"].lower()
