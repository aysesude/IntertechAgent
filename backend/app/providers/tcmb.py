"""TCMB kaynakları — AK 5.1'in "onaylanmış resmî kaynak" karşılığı.

İki uç:
- `TcmbTodayProvider`: today.xml, yalnızca BUGÜNÜN kuru (spot). Tarihsel sunmaz.
- `TcmbEvdsProvider`: EVDS REST API, tarihsel günlük seriler. Ücretsiz API
  anahtarı ister (`EVDS_API_KEY`, evds2.tcmb.gov.tr'den alınır).
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from xml.etree import ElementTree

import requests

from app.core.config import PriceSource
from app.providers.base import PricePoint, ProviderError

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


class TcmbTodayProvider:
    """https://www.tcmb.gov.tr/kurlar/today.xml — sembol, para birimi kodudur
    (ör. 'USD'). Değerleme satış kuru üzerinden yapılır: önce ForexSelling,
    boşsa BanknoteSelling."""

    BASE_URL = "https://www.tcmb.gov.tr/kurlar/today.xml"

    def fetch_series(self, symbol: str, start: date, end: date) -> list[PricePoint]:
        raise ProviderError(
            "tcmb", symbol, "today.xml tarihsel seri sunmaz; tarihsel için EVDS kullanın"
        )

    def fetch_latest(self, symbol: str) -> PricePoint | None:
        try:
            response = requests.get(self.BASE_URL, headers=_HEADERS, timeout=10)
            response.raise_for_status()
            root = ElementTree.fromstring(response.content)
        except (requests.RequestException, ElementTree.ParseError) as exc:
            raise ProviderError("tcmb", symbol, f"today.xml alınamadı: {exc}") from exc

        # Kök öznitelik Date="08/14/2026" — kurun ait olduğu gün.
        date_attr = root.attrib.get("Date")
        price_date = datetime.strptime(date_attr, "%m/%d/%Y").date() if date_attr else date.today()

        for currency in root.findall("Currency"):
            if currency.attrib.get("CurrencyCode") != symbol:
                continue
            value = _first_text(currency, "ForexSelling", "BanknoteSelling")
            if value is None:
                raise ProviderError("tcmb", symbol, "kur alanları boş (tatil günü olabilir)")
            return PricePoint(
                price_date=price_date,
                close_price=Decimal(value),
                source=PriceSource.TCMB,
            )
        return None


def _first_text(element: ElementTree.Element, *tags: str) -> str | None:
    for tag in tags:
        node = element.find(tag)
        if node is not None and node.text and node.text.strip():
            return node.text.strip()
    return None


class TcmbEvdsProvider:
    """EVDS tarihsel seriler — sembol, EVDS seri kodudur
    (ör. 'TP.DK.USD.S.YTL' = USD satış kuru).

    Uç nokta EVDS 3'tür (Ocak 2026'da yenilendi): eski
    `evds2.tcmb.gov.tr/service/evds/...` yolu artık API yerine web arayüzünün
    HTML'ini döndürüyor. Anahtar `key` HTTP başlığıyla gönderilir."""

    BASE_URL = "https://evds3.tcmb.gov.tr/igmevdsms-dis"

    def __init__(self, api_key: str | None):
        self.api_key = api_key

    def fetch_series(self, symbol: str, start: date, end: date) -> list[PricePoint]:
        if not self.api_key:
            raise ProviderError(
                "tcmb_evds",
                symbol,
                "EVDS API anahtarı tanımlı değil; .env'e EVDS_API_KEY ekleyin "
                "veya yedek kaynağa (yfinance) düşün",
            )
        url = (
            f"{self.BASE_URL}/series={symbol}"
            f"&startDate={start.strftime('%d-%m-%Y')}&endDate={end.strftime('%d-%m-%Y')}"
            "&type=json"
        )
        # Not: parametreler '?' ile değil doğrudan yol üzerinde taşınır —
        # EVDS'in kendine özgü URL biçimi budur, standart query string değildir.
        try:
            response = requests.get(url, headers={"key": self.api_key}, timeout=30)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderError("tcmb_evds", symbol, f"EVDS isteği başarısız: {exc}") from exc

        field = symbol.replace(".", "_")
        points: list[PricePoint] = []
        for item in payload.get("items", []):
            raw = item.get(field)
            if raw in (None, "", "null"):
                continue  # tatil/hafta sonu — o gün kur yayımlanmaz
            points.append(
                PricePoint(
                    price_date=datetime.strptime(item["Tarih"], "%d-%m-%Y").date(),
                    close_price=Decimal(str(raw)),
                    source=PriceSource.TCMB_EVDS,
                )
            )
        if not points:
            raise ProviderError("tcmb_evds", symbol, f"{start}–{end} aralığında veri dönmedi")
        return points

    def fetch_latest(self, symbol: str) -> PricePoint | None:
        today = date.today()
        points = self.fetch_series(symbol, today - timedelta(days=7), today)
        return points[-1] if points else None
