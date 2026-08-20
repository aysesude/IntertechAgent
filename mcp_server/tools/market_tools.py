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

import functools
import logging
from typing import Any

import anyio.to_thread
from fastmcp import FastMCP

from app.core.config import settings
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


def register(mcp: FastMCP) -> list[str]:
    @mcp.tool(name="search_market_news")
    @tool_handler(timeout=settings.mcp_tool_timeout_rag)
    async def search_market_news(
        query: str,
        top_k: int = 5,
        sirket: str | None = None,
        donem: str | None = None,
        tur: str | None = None,
    ) -> dict[str, Any]:
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
            sirket: Borsa kodu ("ASELS"). Verilirse arama uzayı benzerlik
                hesaplanmadan önce bu şirkete daraltılır — yanlış şirketin
                dokümanını döndürmek yapısal olarak imkânsız hale gelir.
                Emin olunmayan durumda VERİLMEZ: yanlış filtre, doğru doküman
                veritabanında dururken "bulunamadı" dedirtir.
            donem: "2026-Q2" biçiminde çeyrek. Aynı şirketin farklı
                çeyreklerinde farklı rakamlar var; bu alan hangisinin
                istendiğini deterministik olarak işaretler.
            tur: Doküman türü ("bilanco", "haber", "analiz", "duyuru", "makro").

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
        # run_sync anahtar kelimeli argüman almıyor; filtreler partial'a sarılır.
        cagri = functools.partial(
            retriever.retrieve, query, top_k, sirket=sirket, donem=donem, tur=tur
        )
        results = await anyio.to_thread.run_sync(cagri, abandon_on_cancel=True)

        if not results:
            raise ToolFailure(ToolErrorCode.NOT_FOUND, NOT_FOUND_MESSAGE)

        return {"results": results}

    return ["search_market_news"]
