"""Piyasa verisi sağlayıcı katmanı.

Kurallar (bkz. docs/DATA.md):
- Sağlayıcılar SAFTIR: DB'ye dokunmaz, global durum tutmaz, `print` etmez.
- Hata durumunda `ProviderError` fırlatılır; sessizce yutmak (`except: pass`)
  yasaktır — karar (yeniden dene / logla / düş) çağıranındır.
- Fiyatlar her zaman `Decimal`'dir; `float` fiyat taşınmaz.
"""

from app.providers.base import PricePoint, PriceProvider, ProviderError

__all__ = ["PricePoint", "PriceProvider", "ProviderError"]
