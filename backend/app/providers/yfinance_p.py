"""yfinance sağlayıcısı: BIST hisseleri ('THYAO.IS'), kurlar ('USDTRY=X') ve
ons vadeli metaller ('GC=F', 'SI=F', 'PL=F').

Not: Yahoo resmî/onaylı kaynak değildir (AK 5.1). Hisse için pratik tek
ücretsiz kaynak olduğundan kullanılır; kur için yalnızca EVDS anahtarı yoksa
yedektir. Kaynak her satırda `source` olarak işaretlendiği için bu ayrım
sonradan SQL ile denetlenebilir.

2026-08-25 eki — `fetch_news`: aynı sağlayıcı, aynı ücretsiz/anahtarsız
erişimle Yahoo Finance'in haber akışını da sunuyor. `app/services/
macro_news_ingest.py` bunu Döviz ve Kıymetli Maden sınıfları için canlı,
portföye göre kişiselleştirilmiş makro haber kaynağı olarak kullanır (bkz. o
dosyanın docstring'i — neden RAG değil, neden istek anında değil batch).
"""

import math
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from app.core.config import PriceSource
from app.providers.base import NewsItem, PricePoint, ProviderError
from app.providers.universe import TROY_OUNCE_GRAMS

_PRICE_QUANT = Decimal("0.000001")

# yfinance>=0.2.43 haber şemasını "content" altında iç içe döner (title,
# pubDate ISO metin, provider.displayName, canonicalUrl.url). Sürüm
# geçişinde eski düz şema (title, providerPublishTime unix saniye, publisher,
# link) da görülebiliyor — ikisi de desteklenir, hiçbiri varsayılmaz; alan
# eksikse o haber öğesi ATLANIR (uydurma yok, bkz. CLAUDE.md §4).


def _parse_news_item(raw: dict) -> "NewsItem | None":
    """Tek bir ham yfinance haber öğesini `NewsItem`'e çevirir. Zorunlu dört
    alandan (başlık, url, yayın tarihi, kaynak) biri bile çıkarılamazsa
    `None` döner — çağıran taraf bunu sessizce atlar."""
    content = raw.get("content") if isinstance(raw.get("content"), dict) else None

    if content is not None:
        title = content.get("title")
        provider = content.get("provider") or {}
        publisher = provider.get("displayName") if isinstance(provider, dict) else None
        url_obj = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
        url = url_obj.get("url") if isinstance(url_obj, dict) else None
        pub_date_raw = content.get("pubDate") or content.get("displayTime")
        published_at = _parse_iso_timestamp(pub_date_raw) if pub_date_raw else None
    else:
        title = raw.get("title")
        publisher = raw.get("publisher")
        url = raw.get("link")
        provider_publish_time = raw.get("providerPublishTime")
        published_at = (
            datetime.fromtimestamp(provider_publish_time, tz=timezone.utc)
            if isinstance(provider_publish_time, int | float)
            else None
        )

    if not title or not url or not published_at:
        return None
    return NewsItem(
        headline=title,
        source=publisher or "Yahoo Finance",
        url=url,
        published_at=published_at,
    )


def _parse_iso_timestamp(value: str) -> datetime | None:
    """ISO 8601 metnini `datetime`'a çevirir. `Z` soneki `fromisoformat`
    tarafından desteklenmez (Python < 3.11'de kesin, 3.11'de bile bazı
    varyantlarda sorunlu) — `+00:00`'a çevrilir."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


class YFinanceProvider:
    def fetch_series(self, symbol: str, start: date, end: date) -> list[PricePoint]:
        frame = self._history(symbol, start=start, end=end + timedelta(days=1))
        points = self._frame_to_points(symbol, frame)
        if not points:
            raise ProviderError("yfinance", symbol, f"{start}–{end} aralığında veri dönmedi")
        return points

    def fetch_latest(self, symbol: str) -> PricePoint | None:
        # 5 gün: hafta sonu/tatilde de son işlem gününü yakalamak için.
        frame = self._history(symbol, period="5d")
        points = self._frame_to_points(symbol, frame)
        return points[-1] if points else None

    def fetch_news(self, symbol: str, limit: int = 5) -> list[NewsItem]:
        """Sembol için son haber başlıklarını çeker (bkz.
        app/services/macro_news_ingest.py). Boş liste "haber yok" anlamına
        gelir; bu bir hata değildir. Sağlayıcı çağrısı başarısız olursa
        `ProviderError` fırlatılır — `fetch_series`/`fetch_latest` ile aynı
        kalıp."""
        import yfinance

        try:
            raw_items = yfinance.Ticker(symbol).news or []
        except Exception as exc:  # yfinance kendi iç hatalarını çeşitli tiplerle atar
            raise ProviderError("yfinance", symbol, f"haber istegi basarisiz: {exc}") from exc

        items = [item for raw in raw_items if (item := _parse_news_item(raw)) is not None]
        items.sort(key=lambda item: item.published_at, reverse=True)
        return items[:limit]

    def _history(self, symbol: str, **kwargs):
        import yfinance

        try:
            frame = yfinance.Ticker(symbol).history(auto_adjust=False, **kwargs)
        except Exception as exc:  # yfinance kendi iç hatalarını çeşitli tiplerle atar
            raise ProviderError("yfinance", symbol, f"istek başarısız: {exc}") from exc
        return frame

    def _frame_to_points(self, symbol: str, frame) -> list[PricePoint]:
        points: list[PricePoint] = []
        for index, row in frame.iterrows():
            close = float(row["Close"])
            if math.isnan(close):
                continue
            points.append(
                PricePoint(
                    price_date=index.date(),
                    close_price=Decimal(str(close)).quantize(_PRICE_QUANT, rounding=ROUND_HALF_UP),
                    source=PriceSource.YFINANCE,
                )
            )
        return points


class YFinanceGramMetalProvider:
    """Ons-USD vadeli fiyatı gram-TRY'ye çevirir:
    gram = ons / 31.1034768 × o günün USDTRY kuru.

    Kur *o günün* kurudur (bugünkü değil) — tarihsel seride bugünkü kuru
    kullanmak seriyi bozar. Kurun olmadığı günler (takvim uyuşmazlığı) atlanır.
    """

    def __init__(self, base: YFinanceProvider | None = None, fx_symbol: str = "USDTRY=X"):
        self._base = base or YFinanceProvider()
        self._fx_symbol = fx_symbol

    def fetch_series(self, symbol: str, start: date, end: date) -> list[PricePoint]:
        ounce_points = self._base.fetch_series(symbol, start, end)
        fx_by_date = {
            p.price_date: p.close_price
            for p in self._base.fetch_series(self._fx_symbol, start, end)
        }
        points = [
            PricePoint(
                price_date=p.price_date,
                close_price=(p.close_price / TROY_OUNCE_GRAMS * fx_by_date[p.price_date]).quantize(
                    _PRICE_QUANT, rounding=ROUND_HALF_UP
                ),
                source=PriceSource.YFINANCE,
            )
            for p in ounce_points
            if p.price_date in fx_by_date
        ]
        if not points:
            raise ProviderError(
                "yfinance", symbol, "ons serisi ile USDTRY serisi hiçbir günde kesişmedi"
            )
        return points

    def fetch_latest(self, symbol: str) -> PricePoint | None:
        ounce = self._base.fetch_latest(symbol)
        fx = self._base.fetch_latest(self._fx_symbol)
        if ounce is None or fx is None:
            return None
        return PricePoint(
            price_date=ounce.price_date,
            close_price=(ounce.close_price / TROY_OUNCE_GRAMS * fx.close_price).quantize(
                _PRICE_QUANT, rounding=ROUND_HALF_UP
            ),
            source=PriceSource.YFINANCE,
        )
