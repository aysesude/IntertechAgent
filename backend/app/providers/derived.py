"""Türetilmiş fiyatlar: bir varlığın serisi, başka bir varlığın serisinden
sabit katsayıyla hesaplanır.

Örnek: çeyrek altın = gram altın × 1.6030 (1.75 g × 0.916 milyem). Katsayı
şemada durur (assets.derived_factor); bu modül yalnızca hesabı yapar.
"""

from decimal import ROUND_HALF_UP, Decimal

from app.core.config import PriceSource
from app.providers.base import PricePoint

_PRICE_QUANT = Decimal("0.000001")


def derive_points(base_points: list[PricePoint], factor: Decimal) -> list[PricePoint]:
    """Kaynak serinin her gününü katsayıyla çarpar; source='derived' işaretler."""
    return [
        PricePoint(
            price_date=p.price_date,
            close_price=(p.close_price * factor).quantize(_PRICE_QUANT, rounding=ROUND_HALF_UP),
            source=PriceSource.DERIVED,
        )
        for p in base_points
    ]
