"""yfinance sağlayıcısı: BIST hisseleri ('THYAO.IS'), kurlar ('USDTRY=X') ve
ons vadeli metaller ('GC=F', 'SI=F', 'PL=F').

Not: Yahoo resmî/onaylı kaynak değildir (AK 5.1). Hisse için pratik tek
ücretsiz kaynak olduğundan kullanılır; kur için yalnızca EVDS anahtarı yoksa
yedektir. Kaynak her satırda `source` olarak işaretlendiği için bu ayrım
sonradan SQL ile denetlenebilir.
"""

import math
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.core.config import PriceSource
from app.providers.base import PricePoint, ProviderError
from app.providers.universe import TROY_OUNCE_GRAMS

_PRICE_QUANT = Decimal("0.000001")


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
