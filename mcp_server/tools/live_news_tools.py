"""Canlı piyasa bilgisi tool'ları: KAP bildirimleri ve genel piyasa gündemi.

`search_market_news`'ten (RAG: arşivlenmiş, değişmeyecek bilgi — bilanço
metni, şirket profili, referans) FARKLI bir kapı: bu tool'lar internete o an
çıkar, sonucu veritabanında saklamaz (2026-08-24 kararı: "RAG değişmeyecek
bilgiler içindir, güncel bilgi canlı çekilir"). Piyasa Ajanı sorunun
niteliğine göre bunları RAG ile birlikte kullanabilir.

İŞ BÖLÜMÜ:
- `get_live_kap_disclosures` — ŞİRKETE ÖZEL resmî bildirimler (KAP).
- `get_live_market_headlines` — GENEL piyasa gündemi (BloombergHT son
  dakika). Şirket bazlı haber vermez; nedeni app/providers/bloomberg_ht_p.py
  başlığında ölçümle açıklanıyor.
"""

import functools
import logging
from typing import Any

import anyio.to_thread
from fastmcp import FastMCP

from app.core.config import settings
from app.providers.base import ProviderError
from app.providers.bloomberg_ht_p import BloombergHtProvider
from app.providers.kap_p import KapProvider
from mcp_server.tools._base import ToolErrorCode, ToolFailure, tool_handler

logger = logging.getLogger(__name__)


def register(mcp: FastMCP) -> list[str]:
    @mcp.tool(name="get_live_kap_disclosures")
    @tool_handler(timeout=settings.mcp_tool_timeout_live_news)
    async def get_live_kap_disclosures(sirket: str, limit: int = 5) -> dict[str, Any]:
        """KAP'tan (Kamuyu Aydınlatma Platformu) bir şirketin EN GÜNCEL
        bildirimlerini CANLI olarak çeker. `search_market_news`'ten farklı
        olarak veritabanı/RAG kullanmaz — sonuç saklanmaz, her çağrıda
        yeniden istenir. Resmî bir KAP API'si yoktur; bu tool `pykap`
        kütüphanesi üzerinden KAP'ın web sayfalarını okur (bkz.
        app/providers/kap_p.py, AK 5.1 çekincesi).

        Ne zaman kullanılır: "ASELSAN'ın son KAP bildirimleri neler",
        "bu şirket bugün açıklama yaptı mı" gibi GÜNCELLİK gerektiren,
        arşivde henüz olmayan bilgi soruları.

        Ne zaman kullanılmaz: geçmiş çeyrek bilançosunun içeriği/rakamları
        veya şirket genel profili (search_market_news — arşivlenmiş, kaynak
        gösterilmiş belge); kullanıcının kendi portföyü (get_portfolio_news).

        Args:
            sirket: Borsa kodu ("ASELS"). Sorgudan çıkarım ajan tarafında
                yapılır (bkz. agents/market_query.py), bu tool serbest metin
                kabul etmez.
            limit: En fazla kaç bildirim getirileceği.

        Returns:
            Başarılı: {"success": true, "data": {"disclosures": [{"baslik":
            "Finansal Rapor (6 Aylık)", "tarih": "04.08.2026",
            "url": "https://www.kap.org.tr/tr/Bildirim/1643141"}, ...]}}.
            Son 60 günlük pencerede arar, en yeni en üstte.
            Hata: PROVIDER_UNAVAILABLE (KAP'a ulaşılamadı/pykap kurulu
            değil) · NOT_FOUND (şirket için bu pencerede bildirim yok).
        """
        provider = KapProvider()
        cagri = functools.partial(provider.fetch_latest_disclosures, sirket, limit)
        try:
            disclosures = await anyio.to_thread.run_sync(cagri, abandon_on_cancel=True)
        except ProviderError as exc:
            logger.warning("get_live_kap_disclosures: saglayici hatasi — %s", exc)
            raise ToolFailure(ToolErrorCode.PROVIDER_UNAVAILABLE, detail=str(exc)) from exc

        if not disclosures:
            raise ToolFailure(
                ToolErrorCode.NOT_FOUND, "Bu şirket için güncel KAP bildirimi bulunamadı."
            )

        return {
            "disclosures": [
                {
                    "baslik": d.baslik,
                    "tarih": d.tarih.strftime("%d.%m.%Y") if d.tarih else None,
                    "url": d.url,
                }
                for d in disclosures
            ]
        }

    @mcp.tool(name="get_live_market_headlines")
    @tool_handler(timeout=settings.mcp_tool_timeout_live_news)
    async def get_live_market_headlines(limit: int = 8) -> dict[str, Any]:
        """BloombergHT'nin son dakika akışından GENEL piyasa gündemini CANLI
        çeker. Şirkete özel değildir — hangi şirketin sorulduğuna bakmaz,
        piyasanın o günkü gündemini verir.

        Ne zaman kullanılır: "bugün piyasada ne oldu", "son piyasa haberleri
        neler", "gündemde ne var" gibi ŞİRKETSİZ güncellik soruları. Bu
        soruların başka kaynağı yok: RAG haber tutmuyor, KAP ise şirket bazlı.

        Ne zaman kullanılmaz: belirli bir şirketin bildirimi
        (get_live_kap_disclosures) · geçmiş bilanço rakamları veya şirket
        profili (search_market_news) · fiyat/kur (get_current_prices).

        Args:
            limit: En fazla kaç başlık getirileceği.

        Returns:
            Başarılı: {"success": true, "data": {"headlines": [{"baslik":
            "TCMB: ...", "tarih": "24.08.2026 14:38"}, ...],
            "kaynak_url": "https://www.bloomberght.com/sondakika"}}.
            En yeni en üstte. Maddelerin AYRI bağlantısı yoktur (sitede de
            yok), kaynak olarak sayfanın kendisi verilir.
            Hata: PROVIDER_UNAVAILABLE (siteye ulaşılamadı ya da sayfa
            yapısı değiştiği için hiçbir başlık ayrıştırılamadı).
        """
        provider = BloombergHtProvider()
        cagri = functools.partial(provider.fetch_latest_headlines, limit)
        try:
            headlines = await anyio.to_thread.run_sync(cagri, abandon_on_cancel=True)
        except ProviderError as exc:
            logger.warning("get_live_market_headlines: saglayici hatasi — %s", exc)
            raise ToolFailure(ToolErrorCode.PROVIDER_UNAVAILABLE, detail=str(exc)) from exc

        return {
            "headlines": [
                {
                    "baslik": h.baslik,
                    "tarih": h.tarih.strftime("%d.%m.%Y %H:%M") if h.tarih else None,
                }
                for h in headlines
            ],
            "kaynak_url": headlines[0].kaynak_url if headlines else None,
        }

    return ["get_live_kap_disclosures", "get_live_market_headlines"]
