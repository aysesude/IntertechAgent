"""TEFAS fon fiyatları — `tefas-crawler` kütüphanesi üzerinden tarihsel seri.

TEFAS fiyatları 6 ondalıkla yayımlanır; Decimal'e kayıpsız çevrilir
(price_history.close_price bu yüzden Numeric(18,6)'dır).
"""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.core.config import PriceSource
from app.providers.base import PricePoint, ProviderError

_PRICE_QUANT = Decimal("0.000001")


class TefasProvider:
    def fetch_series(self, symbol: str, start: date, end: date) -> list[PricePoint]:
        try:
            from tefas import Crawler
        except ImportError as exc:
            raise ProviderError(
                "tefas", symbol, "tefas-crawler kurulu değil (pip install tefas-crawler)"
            ) from exc

        try:
            frame = Crawler().fetch(
                start=start.isoformat(),
                end=end.isoformat(),
                name=symbol,
                columns=["code", "date", "price"],
            )
        except Exception as exc:  # crawler ağ/parse hatalarını çeşitli tiplerle atar
            raise ProviderError("tefas", symbol, f"TEFAS isteği başarısız: {exc}") from exc

        points: list[PricePoint] = []
        for _, row in frame.iterrows():
            price = row["price"]
            if price is None:
                continue
            row_date = row["date"]
            price_date = row_date.date() if hasattr(row_date, "date") else row_date
            points.append(
                PricePoint(
                    price_date=price_date,
                    close_price=Decimal(str(price)).quantize(_PRICE_QUANT, rounding=ROUND_HALF_UP),
                    source=PriceSource.TEFAS,
                )
            )
        if not points:
            raise ProviderError("tefas", symbol, f"{start}–{end} aralığında veri dönmedi")
        points.sort(key=lambda p: p.price_date)
        return points

    def fetch_latest(self, symbol: str) -> PricePoint | None:
        today = date.today()
        try:
            points = self.fetch_series(symbol, today - timedelta(days=10), today)
        except ProviderError:
            return None
        return points[-1] if points else None
