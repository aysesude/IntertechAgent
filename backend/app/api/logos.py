"""Şirket logosu ucu — `<img src>` ile doğrudan kullanılır.

KİMLİK DOĞRULAMASI İSTEMİYOR, bilerek. İki sebep:

1. `<img>` etiketi `Authorization` başlığı gönderemez. Token'lı bir uç için
   logoyu `fetch` ile alıp blob URL üretmek gerekirdi; bu hem tarayıcı
   önbelleğini devre dışı bırakır hem her logo için ek JS iş yükü getirir.

2. Alternatif olan "SVG'yi JSON içinde gönderip DOM'a gömmek" DAHA KÖTÜ:
   SVG script taşıyabilir ve `dangerouslySetInnerHTML` ile gömmek üçüncü
   taraf içeriğine sayfada kod çalıştırma imkânı verirdi. `<img>` içindeki
   SVG ise tarayıcı tarafından yalıtılır, script çalışmaz.

Kotayı koruyan şey kimlik değil, KÜMENİN SONLU OLMASI: yalnızca evrendeki
hisseler sorgulanıyor (124 sembol) ve her biri ilk çağrıda önbelleğe
düşüyor. Uç, keyfi ticker'lar için genel bir logo proxy'si olarak
kullanılamaz.

Kullanıcıya özel hiçbir bilgi taşımıyor: bir şirketin logosu herkes için
aynı.
"""

from fastapi import APIRouter, HTTPException, Response

from app.services.logo_service import get_logo_svg

router = APIRouter(prefix="/api/logos", tags=["logos"])

# Logolar değişmez; tarayıcı bir hafta boyunca yeniden sormasın.
_CACHE_CONTROL = "public, max-age=604800, immutable"


@router.get("/{symbol}")
def read_logo(symbol: str) -> Response:
    """Sembolün SVG logosu.

    Logo yoksa **404** döner ve bu normal bir sonuçtur: arayüz `onError` ile
    harf rozetine düşer. Boş bir görsel ya da yer tutucu döndürmek, eksik
    logoyu görünmez bir kusura çevirirdi.
    """
    svg = get_logo_svg(symbol)
    if svg is None:
        raise HTTPException(status_code=404, detail=f"{symbol} için logo yok")
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": _CACHE_CONTROL},
    )
