"""Portföy bazlı doküman getirme testleri.

İş analistinin 2026-08 güncellemesi: "portföydeki varlıklarla ilgili GÜNCEL
haber, market bilgileri ve analist yorumlarını çekip LLM'e verirsiniz",
"her bulgu en az bir kaynak dokümana referans verir", "ilgili doküman
bulunamadığında güven düzeyi düşük olarak döner ve durum kullanıcıya açıkça
bildirilir".

Buradaki testler o üç cümlenin kod karşılığını kilitler: doğru varlığa ait
olma (deterministik filtre), güncellik (tarih sıralaması) ve eksikliğin
gizlenmemesi (assets_without_documents + confidence).
"""

from decimal import Decimal

import pytest
from fastmcp import Client, FastMCP

from rag.retriever import Retriever


class _FakeVectorStore:
    """Chroma yerine geçer. `where` filtresini KASITLI OLARAK UYGULAMAZ:
    retriever'ın kendi son filtresinin gerçekten çalıştığını görmek için
    tüm dokümanları döndürür (Chroma'nın doğru davrandığını varsaymak,
    tam da retriever'ın savunmaya çalıştığı hata)."""

    def __init__(self, docs: list[dict]) -> None:
        self.docs = docs
        self.last_where: dict | None = None

    def similarity_search(self, query: str, top_k: int, where: dict | None = None) -> list[dict]:
        self.last_where = where
        return self.docs[:top_k]


def _doc(content: str, *, sirket: str, tarih: str, tur: str = "haber", distance: float = 0.3):
    return {
        "content": content,
        "distance": distance,
        "metadata": {
            "sirket": sirket,
            "tarih": tarih,
            "tur": tur,
            "baslik": f"{sirket} {tarih} {tur}",
            "kaynak": "KAP",
            "kaynak_url": f"https://ornek.test/{sirket}/{tarih}",
        },
    }


def test_groups_documents_by_symbol():
    store = _FakeVectorStore(
        [
            _doc("ASELS haberi", sirket="ASELS", tarih="2026-08-04"),
            _doc("THYAO haberi", sirket="THYAO", tarih="2026-08-14"),
        ]
    )
    gruplar = Retriever(store).retrieve_for_symbols(["ASELS", "THYAO"], top_k_per_symbol=2)

    assert set(gruplar) == {"ASELS", "THYAO"}
    assert gruplar["ASELS"][0]["content"] == "ASELS haberi"
    assert gruplar["THYAO"][0]["content"] == "THYAO haberi"


def test_documents_are_sorted_newest_first():
    """ "Güncel" şartı: benzerlik sırası değil tarih sırası geçerli olmalı.

    Regresyon: eski `retrieve()` yalnızca vektör mesafesine göre sıralıyordu;
    mesafesi daha düşük olan ESKİ bir analiz, yeni bilançonun önüne
    geçebiliyordu.
    """
    store = _FakeVectorStore(
        [
            # Mesafesi en düşük olan (en "yakın") kasıtlı olarak en eski.
            _doc("eski analiz", sirket="THYAO", tarih="2026-04-29", distance=0.1),
            _doc("yeni bilanco", sirket="THYAO", tarih="2026-08-05", distance=0.8),
            _doc("orta haber", sirket="THYAO", tarih="2026-07-01", distance=0.4),
        ]
    )
    gruplar = Retriever(store).retrieve_for_symbols(["THYAO"], top_k_per_symbol=3)

    tarihler = [p["metadata"]["tarih"] for p in gruplar["THYAO"]]
    assert tarihler == ["2026-08-05", "2026-07-01", "2026-04-29"]


def test_foreign_symbols_are_dropped_even_if_store_returns_them():
    """Son filtre: portföyde olmayan varlığın dokümanı asla dönmemeli."""
    store = _FakeVectorStore(
        [
            _doc("ASELS haberi", sirket="ASELS", tarih="2026-08-04"),
            _doc("istenmeyen", sirket="GARAN", tarih="2026-08-10"),
        ]
    )
    gruplar = Retriever(store).retrieve_for_symbols(["ASELS"], top_k_per_symbol=5)

    assert set(gruplar) == {"ASELS"}


def test_type_filter_applies_and_reaches_the_store():
    store = _FakeVectorStore(
        [
            _doc("bilanco parcasi", sirket="ASELS", tarih="2026-08-05", tur="bilanco"),
            _doc("haber parcasi", sirket="ASELS", tarih="2026-08-06", tur="haber"),
        ]
    )
    gruplar = Retriever(store).retrieve_for_symbols(
        ["ASELS"], top_k_per_symbol=5, types=["bilanco"]
    )

    assert [p["metadata"]["tur"] for p in gruplar["ASELS"]] == ["bilanco"]
    # Ön filtre de kurulmuş olmalı: eleme yalnızca Python tarafında yapılırsa
    # Chroma havuzu yanlış türlerle dolar ve doğru doküman havuza hiç girmez.
    assert store.last_where == {
        "$and": [{"sirket": {"$in": ["ASELS"]}}, {"tur": {"$in": ["bilanco"]}}]
    }


def test_per_symbol_limit_is_applied_after_date_sort():
    """Limit en yeniden keser, gelişigüzel değil."""
    store = _FakeVectorStore(
        [
            _doc("a", sirket="THYAO", tarih="2026-01-01"),
            _doc("b", sirket="THYAO", tarih="2026-08-14"),
            _doc("c", sirket="THYAO", tarih="2026-05-05"),
        ]
    )
    gruplar = Retriever(store).retrieve_for_symbols(["THYAO"], top_k_per_symbol=1)

    assert [p["metadata"]["tarih"] for p in gruplar["THYAO"]] == ["2026-08-14"]


def test_symbol_without_documents_is_absent_not_empty():
    """Dokümanı olmayan sembol sözlükte HİÇ yer almamalı.

    Boş listeyle dönseydi çağıran taraf "aradık, sonuç yok" ile "hiç
    aramadık"ı ayırt edemezdi; eksikliğin kullanıcıya bildirilmesi bu ayrıma
    dayanıyor.
    """
    store = _FakeVectorStore([_doc("ASELS haberi", sirket="ASELS", tarih="2026-08-04")])
    gruplar = Retriever(store).retrieve_for_symbols(["ASELS", "XAUTRY"], top_k_per_symbol=2)

    assert "XAUTRY" not in gruplar


def test_empty_symbol_list_short_circuits():
    store = _FakeVectorStore([_doc("x", sirket="ASELS", tarih="2026-08-04")])
    assert Retriever(store).retrieve_for_symbols([]) == {}
    assert store.last_where is None, "bos listede vektor sorgusu hic yapilmamali"


# --------------------------------------------------------------------------
# get_portfolio_news MCP tool'u
# --------------------------------------------------------------------------


class _FakeHolding:
    def __init__(self, symbol, name, asset_class, weight, quantity=Decimal(1)):
        self.symbol = symbol
        self.name = name
        self.asset_class = asset_class
        self.weight_percent = weight
        self.quantity = quantity


class _FakeValuation:
    def __init__(self, holdings):
        self.holdings = holdings


class _FakeRetriever:
    def __init__(self, gruplar):
        self._gruplar = gruplar

    def retrieve_for_symbols(self, symbols, *, top_k_per_symbol=2, types=None, query=None):
        return {s: v for s, v in self._gruplar.items() if s in symbols}


@pytest.fixture()
def market_mcp():
    from mcp_server.tools import market_tools

    mcp = FastMCP("test-finans-mcp")
    market_tools.register(mcp)
    return mcp


def _patch_tool(monkeypatch, holdings, gruplar):
    from mcp_server.tools import market_tools

    monkeypatch.setattr(market_tools, "_get_retriever", lambda: _FakeRetriever(gruplar))
    monkeypatch.setattr(
        market_tools, "fetch_holdings", lambda db, user_id: _FakeValuation(holdings)
    )

    class _NullSession:
        def __enter__(self):
            return None

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(market_tools, "db_session", lambda: _NullSession())


async def test_portfolio_news_reports_uncovered_assets_and_low_confidence(market_mcp, monkeypatch):
    """Kabul kriteri: doküman bulunamayan varlıklar gizlenmez, güven düşer.

    Bugünkü külliyatta altın/döviz/tahvil dokümanı YOK; tipik bir portföyün
    çoğunluğu bu durumda. Sistemin bunu sessizce yutmaması gerekiyor.
    """
    from app.core.config import AssetClass

    holdings = [
        _FakeHolding("ASELS", "Aselsan", AssetClass.STOCK, Decimal("30")),
        _FakeHolding("XAUTRY", "Gram Altin", AssetClass.PRECIOUS_METAL, Decimal("70")),
    ]
    gruplar = {"ASELS": [_doc("ASELS bilanco", sirket="ASELS", tarih="2026-08-05", tur="bilanco")]}
    _patch_tool(monkeypatch, holdings, gruplar)

    async with Client(market_mcp) as client:
        result = await client.call_tool(
            "get_portfolio_news", {"user_id": "11111111-1111-1111-1111-111111111111"}
        )

    data = result.structured_content["data"]
    assert [a["symbol"] for a in data["assets"]] == ["ASELS"]
    assert data["assets_without_documents"] == ["XAUTRY"]
    assert data["covered_weight_percent"] == 30.0
    # Kapsanan ağırlık %50 eşiğinin altında -> düşük güven.
    assert data["confidence"] == "low"


async def test_portfolio_news_exposes_source_fields(market_mcp, monkeypatch):
    """ "Her bulgu en az bir kaynak dokümana referans verir" — başlık, tarih
    ve kaynak alanları düşerse bu kriter yapısal olarak karşılanamaz."""
    from app.core.config import AssetClass

    holdings = [_FakeHolding("THYAO", "Turk Hava Yollari", AssetClass.STOCK, Decimal("100"))]
    gruplar = {"THYAO": [_doc("THYAO bilanco", sirket="THYAO", tarih="2026-08-05", tur="bilanco")]}
    _patch_tool(monkeypatch, holdings, gruplar)

    async with Client(market_mcp) as client:
        result = await client.call_tool(
            "get_portfolio_news", {"user_id": "11111111-1111-1111-1111-111111111111"}
        )

    belge = result.structured_content["data"]["assets"][0]["documents"][0]
    assert belge["baslik"] and belge["tarih"] and belge["kaynak"]
    assert belge["kaynak_url"].startswith("https://")
    assert belge["tur"] == "bilanco"
    # Vektör mesafesi LLM'e verilmez: alaka ölçüsü değil, uydurma güven
    # ifadesine dönüşme riski taşır.
    assert "distance" not in belge


async def test_portfolio_news_returns_not_found_for_empty_portfolio(market_mcp, monkeypatch):
    _patch_tool(monkeypatch, [], {})

    async with Client(market_mcp) as client:
        result = await client.call_tool(
            "get_portfolio_news", {"user_id": "11111111-1111-1111-1111-111111111111"}
        )

    envelope = result.structured_content
    assert envelope["success"] is False
    assert envelope["error"]["code"] == "NOT_FOUND"
