from datetime import datetime, timedelta, timezone

import pytest
from fastmcp import Client, FastMCP

from app.core.config import AssetClass
from app.core.exceptions import ProviderUnavailableError
from app.models import MacroNewsSnapshot
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
        self.cagrilar: list[dict] = []

    def retrieve(
        self,
        query: str,
        top_k: int,
        *,
        sirket: str | None = None,
        donem: str | None = None,
        tur: str | None = None,
    ) -> list[dict]:
        self.cagrilar.append(
            {"query": query, "top_k": top_k, "sirket": sirket, "donem": donem, "tur": tur}
        )
        return self._results


async def test_search_market_news_tool_success(mcp_server, monkeypatch):
    fake_results = [
        {
            "content": "Örnek Şirket net kârı 2,4 milyar TL oldu.",
            "metadata": {"baslik": "Örnek Şirket 2026 2. Çeyrek Finansal Sonuçları"},
            "distance": 0.2,
        }
    ]
    monkeypatch.setattr(market_tools, "_get_retriever", lambda: _FakeRetriever(fake_results))

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
        result = await client.call_tool("search_market_news", {"query": "Bitcoin fiyatı ne kadar"})

    envelope = result.structured_content
    assert envelope["success"] is False
    assert envelope["error"]["code"] == ToolErrorCode.NOT_FOUND.value
    assert (
        envelope["error"]["message"] != DEFAULT_MESSAGES[ToolErrorCode.NOT_FOUND]
    )  # ozellesmis mesaj


async def test_search_market_news_chroma_erisilemezse_provider_unavailable(mcp_server, monkeypatch):
    """Chroma ayakta degilse sozlesme (docs/MCP-TOOLS.md §2) PROVIDER_UNAVAILABLE
    ister: ajan bu kodda zarif duser (son bilinen veriyle devam eder ya da
    durumu soyler). INTERNAL_ERROR donerse ajan bunu kod hatasindan ayirt
    edemez. Eslemeyi tool degil `@tool_handler` yapar; saglayici katmani
    `ProviderUnavailableError` firlatir (bkz. rag/vector_store.py)."""

    def patlat():
        raise ProviderUnavailableError("Chroma connection failed at chroma:8000")

    monkeypatch.setattr(market_tools, "_get_retriever", patlat)

    async with Client(mcp_server) as client:
        result = await client.call_tool("search_market_news", {"query": "herhangi bir soru"})

    envelope = result.structured_content
    assert envelope["success"] is False
    assert envelope["error"]["code"] == ToolErrorCode.PROVIDER_UNAVAILABLE.value
    # Servis istisnasinin ic metni (baglanti adresi dahil) zarfa sizmaz.
    assert envelope["error"]["message"] == DEFAULT_MESSAGES[ToolErrorCode.PROVIDER_UNAVAILABLE]
    assert "chroma" not in envelope["error"]["message"].lower()


async def test_search_market_news_tool_beklenmeyen_hatada_cokmez(mcp_server, monkeypatch):
    """Taksonomiye girmeyen bir hata (kod hatasi, bozuk kurulum) INTERNAL_ERROR
    olur: tool yine de zarf doner, teknik detay kullaniciya sizmaz."""

    def patlat():
        raise RuntimeError("'NoneType' object has no attribute 'query'")

    monkeypatch.setattr(market_tools, "_get_retriever", patlat)

    async with Client(mcp_server) as client:
        result = await client.call_tool("search_market_news", {"query": "herhangi bir soru"})

    envelope = result.structured_content
    assert envelope["success"] is False
    assert envelope["error"]["code"] == ToolErrorCode.INTERNAL_ERROR.value
    assert "nonetype" not in envelope["error"]["message"].lower()


def test_warm_up_gercek_sorguyu_calistirir(monkeypatch):
    """warm_up, sunucu acilirken ilk kullaniciyi beklemeden embedding modelini
    ve Chroma baglantisini yukler (bkz. market_tools.warm_up docstring'i)."""
    fake = _FakeRetriever([])
    monkeypatch.setattr(market_tools, "_get_retriever", lambda: fake)

    calls: list[tuple[str, int]] = []
    fake.retrieve = lambda query, top_k: calls.append((query, top_k))

    market_tools.warm_up()

    assert len(calls) == 1


def test_warm_up_chroma_ayakta_degilse_cokmez(monkeypatch):
    """Isitma sirasinda Chroma ayakta degilse sunucu yine de acilmali; ilk
    gercek istek normal PROVIDER_UNAVAILABLE yolundan gecer."""

    def patlat():
        raise RuntimeError("connection refused")

    monkeypatch.setattr(market_tools, "_get_retriever", patlat)

    market_tools.warm_up()  # istisna firlatmamali


# --- get_macro_news: canli makro haber (2026-08-25 eki) ----------------------
# search_market_news'ten farkli: RAG/Chroma degil, macro_news_snapshot
# tablosunu okur (bkz. app/services/macro_news_service.py) — bu yuzden
# _FakeRetriever degil, gercek test DB'si (db_session fixture) kullanilir.


async def test_get_macro_news_tool_success(mcp_server, db_session):
    db_session.add(
        MacroNewsSnapshot(
            symbol="XAUTRY",
            asset_class=AssetClass.PRECIOUS_METAL,
            headline="Altın rekor seviyeye ulaştı",
            source="Reuters",
            url="https://example.com/altin-rekor",
            published_at=datetime.now(timezone.utc) - timedelta(hours=2),
            fetched_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    async with Client(mcp_server) as client:
        result = await client.call_tool("get_macro_news", {"symbols": ["XAUTRY"]})

    envelope = result.structured_content
    assert envelope["success"] is True
    assert envelope["data"]["news_by_symbol"]["XAUTRY"][0]["headline"] == (
        "Altın rekor seviyeye ulaştı"
    )


async def test_get_macro_news_tool_not_found(mcp_server, db_session):
    # Bos sembol listesi degil, DB'de o sembol icin hic haber yok — uydurma
    # yok, standart NOT_FOUND doner.
    async with Client(mcp_server) as client:
        result = await client.call_tool("get_macro_news", {"symbols": ["USDTRY"]})

    envelope = result.structured_content
    assert envelope["success"] is False
    assert envelope["error"]["code"] == ToolErrorCode.NOT_FOUND.value


async def test_get_macro_news_tool_bos_sembol_listesi_invalid_argument(mcp_server):
    async with Client(mcp_server) as client:
        result = await client.call_tool("get_macro_news", {"symbols": []})

    envelope = result.structured_content
    assert envelope["success"] is False
    assert envelope["error"]["code"] == ToolErrorCode.INVALID_ARGUMENT.value


async def test_get_macro_news_tool_bayat_haberi_disliyor(mcp_server, db_session):
    # Servis katmani (macro_news_service.get_macro_news) settings.
    # macro_news_max_age_days'ten eski satirlari zaten eliyor; tool bunu
    # oldugu gibi tasir — burada uctan uca dogrulaniyor.
    db_session.add(
        MacroNewsSnapshot(
            symbol="USDTRY",
            asset_class=AssetClass.CURRENCY,
            headline="Çok eski dolar haberi",
            source="Test",
            url="https://example.com/eski-dolar",
            published_at=datetime.now(timezone.utc) - timedelta(days=30),
            fetched_at=datetime.now(timezone.utc) - timedelta(days=30),
        )
    )
    db_session.commit()

    async with Client(mcp_server) as client:
        result = await client.call_tool("get_macro_news", {"symbols": ["USDTRY"]})

    envelope = result.structured_content
    assert envelope["success"] is False
    assert envelope["error"]["code"] == ToolErrorCode.NOT_FOUND.value


async def test_filtreler_retriever_a_oldugu_gibi_gecirilir(mcp_server, monkeypatch):
    """sirket/donem/tur tool imzasinda durup retriever'a ulasmazsa deterministik
    filtre sessizce devre disi kalir: arama calisir, yanlis sirketi dondurur ve
    kimse fark etmez. Bu test o sessiz kaybi engeller."""
    fake = _FakeRetriever([])
    monkeypatch.setattr(market_tools, "_get_retriever", lambda: fake)

    async with Client(mcp_server) as client:
        await client.call_tool(
            "search_market_news",
            {
                "query": "ASELSAN ikinci ceyrek",
                "sirket": "ASELS",
                "donem": "2026-Q2",
                "tur": "bilanco",
            },
        )

    assert fake.cagrilar == [
        {
            "query": "ASELSAN ikinci ceyrek",
            "top_k": 5,
            "sirket": "ASELS",
            "donem": "2026-Q2",
            "tur": "bilanco",
        }
    ]


async def test_filtre_verilmezse_retriever_a_none_gider(mcp_server, monkeypatch):
    """Filtresiz cagri eski davranisi korumali: retriever serbest metin
    aramasi yapsin diye alanlar None gitmeli, bos string degil."""
    fake = _FakeRetriever([])
    monkeypatch.setattr(market_tools, "_get_retriever", lambda: fake)

    async with Client(mcp_server) as client:
        await client.call_tool("search_market_news", {"query": "piyasa nasil"})

    assert fake.cagrilar[0]["sirket"] is None
    assert fake.cagrilar[0]["donem"] is None
    assert fake.cagrilar[0]["tur"] is None
