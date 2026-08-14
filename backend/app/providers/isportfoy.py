"""İş Portföy fon API'si — yalnızca SPOT fiyat; TEFAS'ın yedeğidir.

(Berkay'ın canlı değerleme motorundaki uç noktanın temiz taşınması; DB'ye
yazma, model tanımı ve `except: pass` bilerek taşınmadı.)
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import requests

from app.core.config import PriceSource
from app.providers.base import PricePoint, ProviderError

_PRICE_QUANT = Decimal("0.000001")
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


class IsPortfoyProvider:
    BASE_URL = "https://www.isportfoy.com.tr/api/v1/Fund/GetFundDetailHeader"

    def fetch_series(self, symbol: str, start: date, end: date) -> list[PricePoint]:
        raise ProviderError(
            "isportfoy", symbol, "İş Portföy API'si tarihsel seri sunmaz; TEFAS kullanın"
        )

    def fetch_latest(self, symbol: str) -> PricePoint | None:
        try:
            response = requests.get(
                self.BASE_URL, params={"fundCode": symbol}, headers=_HEADERS, timeout=10
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError("isportfoy", symbol, f"istek başarısız: {exc}") from exc

        price = payload.get("Price")
        if not price:
            return None
        return PricePoint(
            price_date=date.today(),
            close_price=Decimal(str(price)).quantize(_PRICE_QUANT, rounding=ROUND_HALF_UP),
            source=PriceSource.ISPORTFOY,
        )
