"""Sağlayıcı sözleşmesi: tüm kaynaklar (TCMB, yfinance, TEFAS, İş Portföy,
sentetik) aynı arayüzü konuşur. Dummy <-> canlı geçişi bu sayede konfigürasyon
meselesidir (CLAUDE.md A1 varsayımının kod karşılığı)."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

from app.core.config import PriceSource


class ProviderError(Exception):
    """Bir sağlayıcı istenen veriyi veremedi.

    Mesaj aksiyon aldırmalıdır: neyin başarısız olduğu + çağıranın ne
    yapabileceği. Çağıran taraf (ingest servisi) loglar ve zincirdeki bir
    sonraki sağlayıcıya düşer; asla sessizce yutulmaz.
    """

    def __init__(self, provider: str, symbol: str, message: str):
        self.provider = provider
        self.symbol = symbol
        super().__init__(f"[{provider}] {symbol}: {message}")


@dataclass(frozen=True)
class PricePoint:
    """Tek bir günün kapanış fiyatı. `close_price` Decimal'dir, float DEĞİL —
    para float'la taşınmaz (yuvarlama hataları birikir)."""

    price_date: date
    close_price: Decimal
    source: PriceSource


@dataclass(frozen=True)
class NewsItem:
    """Tek bir canlı piyasa haberi başlığı (bkz. providers/yfinance_p.py
    YFinanceProvider.fetch_news, app/services/macro_news_ingest.py).

    `published_at` her zaman UTC'dir (kaynak sağlayıcı ne verirse versin
    burada normalize edilir) — DB'deki `DateTime(timezone=True)` kolonuyla
    tutarlı kalsın diye."""

    headline: str
    source: str
    url: str
    published_at: datetime


@runtime_checkable
class PriceProvider(Protocol):
    """Tarihsel seri ve/veya anlık fiyat sağlayan kaynak.

    Bir kaynak ikisinden birini sunmuyorsa ilgili metot ProviderError
    fırlatır (ör. TCMB today.xml tarihsel sunmaz, İş Portföy API'si spot
    sunar)."""

    def fetch_series(self, symbol: str, start: date, end: date) -> list[PricePoint]:
        """[start, end] aralığındaki (uçlar dahil) günlük kapanışlar.
        Kaynakta olmayan günler (hafta sonu, tatil) sonuçta bulunmaz."""
        ...

    def fetch_latest(self, symbol: str) -> PricePoint | None:
        """Kaynaktaki en güncel fiyat; kaynak erişilebilir ama sembol için
        veri yoksa None."""
        ...
