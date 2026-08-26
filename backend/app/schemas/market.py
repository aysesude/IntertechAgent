"""Piyasa ekranının okuma şemaları.

Portföy şemalarından ayrı bir dosyada: bunlar KULLANICIYA ÖZEL OLMAYAN
(gösterge şeridi, haber akışı) ya da portföyden türetilmiş ama piyasa
bağlamında sunulan veriler. `portfolio.py` zaten büyük; piyasa ekranı
büyüdükçe orayı daha da şişirmenin bir gerekçesi yok.

TASARIM: her alan ya gerçek bir kaynaktan gelir ya da `None`'dır. Arayüzdeki
"AI özeti", "etki seviyesi", "kaynak sayısı" gibi alanların karşılığı burada
YOKTUR — BloombergHT son dakika akışı yalnızca başlık ve zaman veriyor
(ölçüldü, 2026-08-24). Arayüz o alanları "—" gösterir; doldurulmuş gibi
görünmeleri için model ürettirmek, sohbet tarafında özenle kaldırdığımız
uydurma riskini ekrana taşırdı (CLAUDE.md "Uydurmama").
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.core.config import AssetClass

# `Money`/`MoneyOpt` portfolio.py'de tanımlı ve oradan alınıyor: aynı
# serileştirme kuralı (Decimal -> float, None -> null) iki dosyada
# tekrarlanırsa biri değişip diğeri unutulur.
from app.schemas.portfolio import Money, MoneyOpt


class MarketIndicator(BaseModel):
    """Gösterge şeridindeki tek satır (BIST 100, USD/TRY, gram altın...)."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    asset_class: AssetClass
    price: Money
    # Bir önceki işlem gününe göre değişim. Seride tek gün varsa `None` —
    # sıfır YAZILMAZ, "değişmedi" ile "hesaplanamadı" farklı şeyler.
    change_percent: MoneyOpt = None
    # Fiyatın ait olduğu gün. Bugün olmak zorunda değil (piyasa hafta sonu
    # kapalı); arayüz bunu göstermek zorunda, aksi hâlde olmayan bir tazelik
    # iddia edilmiş olur.
    price_date: date
    source: str
    stale: bool


class MarketIndicatorList(BaseModel):
    model_config = ConfigDict(frozen=True)

    as_of: date
    indicators: list[MarketIndicator] = []
    # Evrende olmayan ya da bu pencerede fiyatı bulunmayan semboller. Sessizce
    # atlanmaz: şeritte eksik bir gösterge varsa nedeni görünür olmalı.
    missing_symbols: list[str] = []


class MarketHeadline(BaseModel):
    """BloombergHT son dakika akışından tek başlık.

    `url` YOK: akıştaki maddelerin ayrı adresi bulunmuyor (ölçüldü), kaynak
    olarak listenin tamamına giden tek bir adres verilir.
    """

    model_config = ConfigDict(frozen=True)

    title: str
    published_at: datetime | None = None


class MarketHeadlineList(BaseModel):
    model_config = ConfigDict(frozen=True)

    headlines: list[MarketHeadline] = []
    source_name: str
    source_url: str


class PortfolioInfluenceRow(BaseModel):
    """Kullanıcının bir pozisyonu ve o pozisyonun günlük hareketi."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    asset_class: AssetClass
    weight_percent: MoneyOpt = None
    change_percent: MoneyOpt = None


class PortfolioInfluenceList(BaseModel):
    model_config = ConfigDict(frozen=True)

    as_of: date
    rows: list[PortfolioInfluenceRow] = []


class MarketCalendarEntry(BaseModel):
    """Yaklaşan bir KAP bildirimi.

    TEK TARİH DEĞİL, PENCERE: KAP dosyalamanın yapılabileceği bir aralık
    yayımlıyor. `due_date` (aralığın sonu) kullanıcı için bağlayıcı olan
    gündür; `start_date` bilgi amaçlı taşınır.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    company: str
    subject: str
    period: str | None = None
    start_date: date | None = None
    due_date: date


class MarketCalendarList(BaseModel):
    model_config = ConfigDict(frozen=True)

    entries: list[MarketCalendarEntry] = []
    source_name: str
    source_url: str
