"""Fiyat serisi tool'ları.

Portföyden bağımsız piyasa verisi: kullanıcı parametresi yok, aynı sembolün
serisi herkes için aynı. Portföy tool'larından ayrı modülde durmasının sebebi
bu — ileride kullanıcıdan bağımsız önbelleğe alınabilir.

Bu tool internete çıkmaz; `price_history` tablosunu okur. Fiyatların tazeliği
günlük toplama işinin sorumluluğudur (`app/services/price_ingest.py`).
"""

from typing import Any

from fastmcp import FastMCP

from app.core.config import Granularity, PriceCurrency, TimeWindow
from app.services.price_service import get_asset_price_history as fetch_price_history
from app.services.price_service import get_current_prices as fetch_current_prices
from app.services.target_price_service import get_target_prices as fetch_target_prices
from mcp_server.tools._base import db_session, tool_handler


def register(mcp: FastMCP) -> list[str]:
    @mcp.tool(name="get_asset_price_history")
    @tool_handler()
    def get_asset_price_history(
        symbols: list[str],
        window: TimeWindow = TimeWindow.M3,
        granularity: Granularity = Granularity.AUTO,
        currency: PriceCurrency = PriceCurrency.TRY,
    ) -> dict[str, Any]:
        """Verilen sembollerin geçmiş fiyat serisini döndürür.

        Ne zaman kullanılır: bir varlığın fiyatının zaman içinde nasıl
        değiştiği soruluyorsa ("altın son 3 ayda ne yaptı", "dolar yükseldi
        mi"); varlık detay grafiği çiziliyorsa. Kullanıcının o varlığa sahip
        olması gerekmez.

        Ne zaman kullanılmaz: kullanıcının o varlıktan ne kadar kazandığı
        soruluyorsa (get_holdings — bu tool kullanıcıyı bilmez), portföyün
        toplam değeri veya getirisi soruluyorsa (get_portfolio_performance),
        portföy endekslerle karşılaştırılacaksa (get_benchmark_comparison),
        güncel haber veya piyasa yorumu soruluyorsa (search_market_news).

        Args:
            symbols: Sembol listesi, ör. ["THYAO", "XAUTRY", "USDTRY"].
                Boş olamaz.
            window: 1m, 3m, 6m, 12m. Varsayılan 3m.
            granularity: auto, daily, weekly, monthly. auto ~60-120 nokta
                hedefler (1m/3m/6m günlük, 12m haftalık). Volatilite hesabı
                yapılacaksa daily zorunludur — haftalık seriden hesaplanan
                volatilite yanlış ölçekte çıkar.
            currency: try (o günün kuruyla TRY'ye çevrilmiş) veya native
                (varlığın kendi para birimi).

        Returns:
            Başarılı: {"success": true, "data": {"as_of": "2026-08-01",
            "window": "3m", "granularity": "daily", "currency": "try",
            "requested_start": "2026-05-03", "actual_start": "2026-05-04",
            "series": {"THYAO": [{"date": "2026-05-04", "close": 310.0}, ...]},
            "unknown_symbols": [], "symbols_without_data": []}}

            Kısmi veri hata sayılmaz: pencerenin tamamı veritabanında yoksa
            eldeki kadarı döner ve actual_start gerçek başlangıcı bildirir.
            Tanınan ama bu pencerede kaydı olmayan sembol
            symbols_without_data ile raporlanır; diğerlerinin serisi etkilenmez.

            as_of veritabanındaki en son fiyat tarihidir, CANLI FİYAT DEĞİLDİR.
            Hafta sonları seride yer almaz; her kova için o kovanın son işlem
            günü değeri kullanılır (ortalama alınmaz).

            Hata: INVALID_ARGUMENT (boş sembol listesi) · NOT_FOUND (hiçbir
            sembol tanınmadı) · INSUFFICIENT_DATA (semboller tanındı ama
            hiçbirinin bu pencerede fiyat kaydı yok — ör. backfill hiç
            çalıştırılmamış).
        """
        with db_session() as db:
            return fetch_price_history(
                db, symbols, window=window, granularity=granularity, currency=currency
            ).model_dump(mode="json")

    @mcp.tool(name="get_current_prices")
    @tool_handler()
    def get_current_prices(symbols: list[str]) -> dict[str, Any]:
        """Verilen sembollerin GÜNCEL (en son kapanış) fiyatını döndürür.

        Ne zaman kullanılır: "dolar ne kadar", "gram altın kaç TL", "euro kuru
        nedir", "THYAO'nun fiyatı ne" gibi ANLIK fiyat soruları. Kullanıcının
        o varlığa sahip olması gerekmez.

        Ne zaman kullanılmaz: fiyatın zaman içindeki seyri soruluyorsa
        (get_asset_price_history), kullanıcının o varlıktan kazancı
        soruluyorsa (get_holdings), haber/bilanço soruluyorsa
        (search_market_news).

        Args:
            symbols: Sembol listesi, ör. ["USDTRY", "XAUTRY"]. Boş olamaz.
                Kur için USDTRY/EURTRY/GBPTRY/CHFTRY, altın için XAUTRY
                (gram), CEYREK/YARIM/TAMALTIN/CUMHUR kullanılır.

        Returns:
            Başarılı: data.prices = [{symbol, name, asset_class, currency,
            price, price_date, source, age_days, stale}] ve data.as_of.
            `price_date` fiyatın ait olduğu gündür — BUGÜN OLMAK ZORUNDA
            DEĞİL: piyasa hafta sonu ve tatilde kapalıdır, o yüzden yanıtta
            tarih mutlaka belirtilmelidir. `stale` true ise fiyat beklenenden
            eskidir ve bu kullanıcıya söylenmelidir. `source` fiyatın hangi
            kaynaktan geldiğini verir (tcmb, yfinance, tefas, synthetic).

            Tanınmayan semboller unknown_symbols, tanınıp fiyatı olmayanlar
            symbols_without_data ile raporlanır; biri diğerini engellemez.

            Hata: INVALID_ARGUMENT (boş liste) · NOT_FOUND (hiçbir sembol
            tanınmadı).
        """
        with db_session() as db:
            return fetch_current_prices(db, symbols).model_dump(mode="json")

    @mcp.tool(name="get_target_prices")
    @tool_handler()
    def get_target_prices(symbols: list[str]) -> dict[str, Any]:
        """Verilen sembollerin bilinen analist HEDEF FİYATINI/tavsiyesini
        döndürür (ör. Şeker Yatırım "Tavsiye Listesi").

        Ne zaman kullanılır: "GARAN'ın hedef fiyatı ne", "ASELS için analist
        tavsiyesi ne" gibi sorular. Bu GÜNCEL PİYASA FİYATI DEĞİLDİR —
        analistin belirlediği, GEÇMİŞTE raporlanmış bir hedeftir
        (get_current_prices ile karıştırılmaz).

        Ne zaman kullanılmaz: kullanıcının kendisinden GELECEK tahmini
        isteniyorsa (bu tool yalnızca zaten raporlanmış rakamı okur, kendi
        tahmin üretmez); güncel fiyat soruluyorsa (get_current_prices).

        Args:
            symbols: Sembol listesi, ör. ["GARAN", "ASELS"]. Boş olamaz.

        Returns:
            Başarılı: data.records = [{symbol, institution, recommendation,
            target_price, currency, price_at_report, previous_target_price,
            revision_direction, horizon_months, report_date, source_url}].
            Bir sembol için birden fazla kurum kaydı olabilir. Tanınmayan
            semboller unknown_symbols, tanınıp hedef fiyatı olmayanlar
            symbols_without_data ile raporlanır.

            `report_date` kaynağın kendi sayfa/rapor tarihidir — ANLIK
            DEĞİL, yanıtta mutlaka gösterilmelidir (AK 5.1).

            Hata: INVALID_ARGUMENT (boş liste) · NOT_FOUND (hiçbir sembol
            tanınmadı).
        """
        with db_session() as db:
            return fetch_target_prices(db, symbols)

    return ["get_asset_price_history", "get_current_prices", "get_target_prices"]
