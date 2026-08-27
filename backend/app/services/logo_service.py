"""Şirket logolarını logostream.dev'den getirir.

NEDEN PROXY. Anahtar query string'de gidiyor (ölçüldü: header ile "Missing
API Key", `?key=` ile "Invalid API Key"). Tarayıcıdan `<img src="...?key=">`
yazsaydık anahtar sayfayı açan herkese görünür ve kotayı üçüncü şahıslar
harcardı. Anahtar burada, sunucuda kalıyor.

YALNIZCA HİSSE SORGULANIR. Faz 0 ölçümü (27 Ağustos 2026, 141 varlık): BIST
97/103, ABD 21/21 gerçek logo. Ama TEFAS fon kodları üç harfli ve başka
borsalarda gerçek ticker — `IOO`, `AKE`, `TCD`, `TI2`, `AFT`, `GTA`, `BHE`
için logo dönüyor ve bunlar BAŞKA ŞİRKETLERİN logosu. Kanıt bölünmenin
kendisi: `AK2`/`APT`/`AYR` yer tutucu döndü, yani logostream'de TEFAS fonu
yok. Bir İş Portföy fonunun yanına iShares logosu koymak, hiç logo
koymamaktan kötü olurdu.

Döviz ve kıymetli madende zaten kapsam yok (0/4 ve 1/8).
"""

import threading
from typing import Final

import requests

from app.core.config import AssetClass, settings
from app.providers.universe import SPEC_BY_SYMBOL

_BASE_URL: Final = "https://api.logostream.dev/stocks/symbol/{symbol}"
_TIMEOUT_SN: Final = 8

# Yer tutucunun imzası.
#
# Logo bulunamadığında servis 404 DEĞİL, 200 ile sabit `#1E1E1E` kare üzerine
# sembolün ilk üç harfini basan bir SVG döndürüyor. Ayırt edilmezse arayüz
# her eksik logo için koyu gri bir kare gösterir ve bunun bir yer tutucu
# olduğu hiçbir yerde anlaşılmaz — üstelik o koyu kare açık temaya da uymaz.
#
# Boyuta bakmak YETMEZ: gerçek logolar 489-9698 bayt arasında değişiyor ve
# yer tutucu her sembolde 266 bayt ama farklı içerikte. Ayıraç zeminin
# rengi.
_PLACEHOLDER_MARKER: Final = b'fill="#1E1E1E"'

# Logolar değişmez; süreç ömrü boyunca bir kez çekilir.
#
# Sorgulanabilir sembol kümesi evrenle SINIRLI (124 hisse), dolayısıyla bu
# önbellek dolduğunda sağlayıcıya giden istek sayısı da sıfırlanır. Uç
# kimlik doğrulaması istemiyor (bkz. api/logos.py) ve onu güvenli kılan da
# bu: uçtan geçilebilecek sembol sayısı sonlu ve hepsi önbelleğe düşüyor.
_cache: dict[str, bytes | None] = {}
_lock = threading.Lock()


def _logolu_sinif(symbol: str) -> bool:
    """Bu sembol için logo sorgulanmalı mı — yalnızca GERÇEK hisse.

    Sınıfa bakmak YETMEZ: fonlar ekonomik riskine göre sınıflanıyor
    (`universe._FUND_ASSET_CLASS`), dolayısıyla `AFT`, `TI2`, `TCD` ve `BHE`
    de `AssetClass.STOCK`. Testle yakalandı — sınıf ayıracıyla bu dört fon
    sağlayıcıya gidiyor ve başka şirketlerin logosunu getiriyordu.

    Ayıraç `sub_type`: fonun her zaman bir alt türü var (equity_fund,
    hedge_fund, bond_fund...), borsada işlem gören hissenin yok.
    """
    spec = SPEC_BY_SYMBOL.get(symbol)
    return spec is not None and spec.asset_class is AssetClass.STOCK and spec.sub_type is None


def temizle_onbellek() -> None:
    """Önbelleği boşaltır. YALNIZCA TESTLER İÇİN."""
    with _lock:
        _cache.clear()


def get_logo_svg(symbol: str) -> bytes | None:
    """Sembolün SVG logosu; yoksa `None`.

    `None` üç durumda döner ve üçü de arayüzde AYNI sonucu verir (harf
    rozeti): sembol evrende yok, hisse değil, ya da sağlayıcıda logosu yok.
    Ayrı ayrı hata üretmenin çağırana faydası olmazdı.

    Ağ hatası da `None` döndürür — logo bir süs; yokluğu sayfayı
    engellememeli (zarif düşüş).
    """
    sembol = symbol.upper()

    with _lock:
        if sembol in _cache:
            return _cache[sembol]

    if not settings.logostream_api_key or not _logolu_sinif(sembol):
        with _lock:
            _cache[sembol] = None
        return None

    sonuc: bytes | None = None
    try:
        yanit = requests.get(
            _BASE_URL.format(symbol=sembol),
            params={"key": settings.logostream_api_key},
            timeout=_TIMEOUT_SN,
        )
        if yanit.status_code == 200 and _PLACEHOLDER_MARKER not in yanit.content:
            sonuc = yanit.content
    except requests.RequestException:
        # Ağ hatası ÖNBELLEĞE YAZILMAZ: geçici bir kesinti yüzünden logo
        # süreç ömrü boyunca kayıp kalmamalı.
        return None

    with _lock:
        _cache[sembol] = sonuc
    return sonuc
