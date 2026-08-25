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
from uuid import UUID

import anyio.to_thread
from fastmcp import FastMCP

from app.core.config import settings
from app.services.macro_news_service import get_macro_news as fetch_macro_news
from app.services.portfolio_service import get_holdings_valuation as fetch_holdings
from mcp_server.tools._base import ToolErrorCode, ToolFailure, db_session, tool_handler
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
        logger.info("RAG retriever hazırlanıyor (embedding modeli + Chroma bağlantısı)...")
        _retriever = Retriever()
        logger.info("RAG retriever hazır.")
    return _retriever


def warm_up() -> None:
    """Sunucu AÇILIRKEN (ilk kullanıcı sorgusundan önce) bir kez çağrılır:
    embedding modelini ve Chroma bağlantısını önceden yükler.

    Neden gerekli: bu yükleme ~30-60 saniye sürüyor. Isıtma olmadan bu süre
    ilk kullanıcının sorgusuna biniyor; `agents/base.py::call_mcp_tool`'da
    istemci tarafı zaman aşımı olmadığı için (docs/MCP-TOOLS.md §10) istek
    ne hata ne yanıt döner — SSE bağlantısı çoğunlukla ara sunucu/tarayıcı
    tarafından süresi dolmuş sayılıp sessizce kesilir, kullanıcı "hiç yanıt
    gelmedi" görür (ölçümle doğrulandı).

    Chroma bu sırada ayakta değilse hata yutulur: sunucu yine de açılır,
    ilk gerçek istek normal hata yolundan (PROVIDER_UNAVAILABLE) geçer —
    ısıtma bir gereklilik değil, bir optimizasyondur."""
    try:
        retriever = _get_retriever()
        retriever.retrieve("ısınma sorgusu", top_k=1)
        logger.info("RAG isinma sorgusu tamamlandi.")
    except Exception:
        logger.exception("RAG isinma sorgusu basarisiz (Chroma ayakta olmayabilir)")


def _document_payload(parca: dict) -> dict[str, Any]:
    """Doküman parçasını LLM'e verilecek asgari alanlara indirger.

    Kaynak alanları (`baslik`, `tarih`, `kaynak`, `kaynak_url`) KASITLI olarak
    içeride: iş analistinin kabul kriteri "her bulgu en az bir kaynak dokümana
    referans verir" diyor. Bu alanlar düşerse ajan bulgusunu kaynağa
    bağlayamaz ve kriter yapısal olarak karşılanamaz hale gelir.

    `distance` dışarı verilmez: vektör mesafesi bir alaka ölçüsü değil (bkz.
    config.rag_distance_threshold'daki ölçüm notu) ve LLM'e verilirse
    "%80 alakalı" gibi uydurma güven ifadelerine dönüşme riski taşır.
    """
    metadata = parca.get("metadata") or {}
    return {
        "tur": metadata.get("tur"),
        "baslik": metadata.get("baslik"),
        "tarih": metadata.get("tarih"),
        "kaynak": metadata.get("kaynak"),
        "kaynak_url": metadata.get("kaynak_url"),
        "content": parca.get("content"),
    }


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
            Hata: {"success": false, "error": {"code": "NOT_FOUND"}} —
            veritabanında sorguyla yeterince alakalı bir kayıt yoksa;
            {"code": "PROVIDER_UNAVAILABLE"} — Chroma'ya ulaşılamıyorsa
            (sözleşme §2; `rag/vector_store.py` `ProviderUnavailableError`
            fırlatır, `@tool_handler` otomatik eşler).
        """
        # abandon_on_cancel=True: @tool_handler'daki settings.mcp_tool_timeout_rag
        # süresi dolunca çağıran taraf beklemeden TIMEOUT alsın. Bu olmadan
        # anyio, thread bitene kadar iptali erteliyor — 60 sn'lik zaman aşımı
        # ısınmamış (soğuk) bir yüklemede fiilen işlemiyordu (ölçümle
        # doğrulandı: bir istek 106 sn sürüp yine de "OK" döndü).
        retriever = await anyio.to_thread.run_sync(_get_retriever, abandon_on_cancel=True)
        results = await anyio.to_thread.run_sync(
            retriever.retrieve, query, top_k, abandon_on_cancel=True
        )

        if not results:
            raise ToolFailure(ToolErrorCode.NOT_FOUND, NOT_FOUND_MESSAGE)

        return {"results": results}

    @mcp.tool(name="get_portfolio_news")
    @tool_handler(timeout=settings.mcp_tool_timeout_rag)
    async def get_portfolio_news(
        user_id: UUID,
        per_asset: int | None = None,
        types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Kullanıcının portföyünde FİİLEN BULUNAN varlıklar için güncel
        bilanço, analist yorumu ve haber dokümanlarını getirir.

        Ne zaman kullanılır: "portföyümle ilgili haberler var mı",
        "varlıklarımda son durum ne", "hisselerimin bilançoları nasıl geldi"
        gibi kullanıcının KENDİ portföyünü piyasa gelişmeleriyle
        ilişkilendiren sorular. Risk/strateji değerlendirmesinin
        gerekçelendirilmesi için de bu tool kullanılır: her bulgunun bir
        kaynak dokümana dayanması gerekir.

        Ne zaman kullanılmaz: portföyden bağımsız genel piyasa/şirket
        soruları (search_market_news), portföyün sayısal özeti
        (get_portfolio_summary), risk ölçümü (get_risk_assessment).

        Dokümanlar varlık sembolüne göre DETERMİNİSTİK olarak filtrelenir
        (serbest metin benzerliğiyle değil) ve her varlık içinde en yeniden
        en eskiye sıralanır. Portföyde olmayan bir varlığın dokümanı asla
        dönmez.

        Args:
            user_id: Portföyü okunacak kullanıcının UUID'si.
            per_asset: Varlık başına en fazla kaç doküman parçası
                döndürüleceği. Verilmezse yapılandırmadaki varsayılan.
            types: İstenen doküman türleri (`bilanco`, `analiz`, `haber`,
                `duyuru`). Verilmezse yapılandırmadaki varsayılan küme.
                `makro` desteklenmez: makro dokümanlar belirli bir varlığa
                bağlı değildir.

        Returns:
            Başarılı: {"success": true, "data": {"assets": [{"symbol", "name",
            "asset_class", "weight_percent", "documents": [{"tur", "baslik",
            "tarih", "kaynak", "kaynak_url", "content"}]}], "assets_without_documents":
            [...], "covered_weight_percent": 0.0, "confidence": "low"|"normal"}}.
            `confidence` "low" ise portföyün büyük kısmı için kaynak doküman
            YOKTUR ve bu durum kullanıcıya açıkça bildirilmelidir.
            Hata: {"code": "NOT_FOUND"} — kullanıcı/portföy yoksa ya da
            portföyde hiç varlık yoksa; {"code": "PROVIDER_UNAVAILABLE"} —
            Chroma'ya ulaşılamıyorsa.
        """
        with db_session() as db:
            valuation = fetch_holdings(db, user_id)

        positions = [h for h in valuation.holdings if h.quantity > 0]
        if not positions:
            raise ToolFailure(
                ToolErrorCode.NOT_FOUND,
                "Portföyünüzde doküman aranabilecek bir varlık bulunamadı.",
            )

        limit = per_asset if per_asset is not None else settings.portfolio_news_per_asset
        istenen_turler = types if types is not None else settings.portfolio_news_types

        retriever = await anyio.to_thread.run_sync(_get_retriever, abandon_on_cancel=True)
        symbols = [h.symbol for h in positions]
        grouped = await anyio.to_thread.run_sync(
            lambda: retriever.retrieve_for_symbols(
                symbols, top_k_per_symbol=limit, types=istenen_turler
            ),
            abandon_on_cancel=True,
        )

        assets: list[dict[str, Any]] = []
        without: list[str] = []
        covered_weight = 0.0
        for holding in positions:
            parcalar = grouped.get(holding.symbol, [])
            if not parcalar:
                without.append(holding.symbol)
                continue
            covered_weight += float(holding.weight_percent or 0)
            assets.append(
                {
                    "symbol": holding.symbol,
                    "name": holding.name,
                    "asset_class": holding.asset_class.value,
                    "weight_percent": float(holding.weight_percent or 0),
                    "documents": [_document_payload(p) for p in parcalar],
                }
            )

        # Güven düzeyi ÖLÇÜLEN kapsama göre belirlenir, tahminle değil:
        # dokümanla desteklenen varlıkların portföy ağırlığı eşiğin altındaysa
        # çıktı "düşük güven" damgasını yer. Kabul kriteri: "ilgili doküman
        # bulunamadığında güven düzeyi düşük döner ve kullanıcıya bildirilir."
        esik = settings.portfolio_news_low_confidence_weight_percent
        confidence = "normal" if covered_weight >= esik else "low"

        return {
            "assets": assets,
            "assets_without_documents": without,
            "covered_weight_percent": round(covered_weight, 2),
            "confidence": confidence,
        }

    @mcp.tool(name="get_macro_news")
    @tool_handler()
    def get_macro_news(symbols: list[str]) -> dict[str, Any]:
        """Verilen sembollerin CANLI (yfinance haber akışından, günlük
        toplama işiyle çekilmiş) güncel piyasa haberlerini döndürür.

        `search_market_news`'ten farkı: o RAG'daki (statik, donmuş) dokümanı
        arar; bu ise `macro_news_snapshot`taki, `data/macro_news_update.py`
        ile periyodik tazelenen GERÇEK/GÜNCEL haberi okur. Yalnızca Döviz ve
        Kıymetli Maden sembolleri için veri vardır (bkz.
        app/providers/universe.py:yfinance_news_ticker) — Hisse zaten
        `get_portfolio_news` ile kapsanıyor, Tahvil/Nakit'in (TEFAS
        fonları/mevduat) Yahoo'da karşılığı yok.

        Ne zaman kullanılır: risk/strateji ajanının Tahvil/Döviz/Altın/Nakit
        için makro bağlam ihtiyacı (bkz. risk_signals.md
        "makro_gelişmeler"). Türetilmiş varlıklar (ör. çeyrek altın)
        tabanlarının sembolü altında saklanır — çağıran taraf
        `app.providers.universe.macro_news_key` ile bu eşlemeyi kendisi
        yapmalıdır, bu tool sembolü OLDUĞU GİBİ arar, eşleme yapmaz.

        Args:
            symbols: İç sembol listesi (ör. ["XAUTRY", "USDTRY"]). Boş olamaz.

        Returns:
            Başarılı: {"success": true, "data": {"news_by_symbol":
            {"XAUTRY": [{"headline", "source", "url", "published_at"}, ...]}}}.
            Yalnızca haberi bulunan semboller anahtar olarak görünür; hiçbir
            sembolde güncel haber yoksa NOT_FOUND döner.
            Hata: {"code": "INVALID_ARGUMENT"} — boş sembol listesi;
            {"code": "NOT_FOUND"} — hiçbir sembol için (max_age_days içinde
            yayımlanmış) güncel haber yok.
        """
        if not symbols:
            raise ToolFailure(ToolErrorCode.INVALID_ARGUMENT, "En az bir sembol gerekli.")

        with db_session() as db:
            grouped = fetch_macro_news(db, symbols)

        if not grouped:
            raise ToolFailure(
                ToolErrorCode.NOT_FOUND, "İstenen semboller için güncel canlı haber bulunamadı."
            )

        return {"news_by_symbol": grouped}

    return ["search_market_news", "get_portfolio_news", "get_macro_news"]
