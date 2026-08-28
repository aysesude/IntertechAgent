"""Piyasa ekranının okuma servisi: gösterge şeridi ve portföy etkisi.

`price_service`'i SARMALAR, onun yerine geçmez: fiyat okumanın tek yeri hâlâ
orası. Buradaki ek, ekranın ihtiyaç duyduğu ama fiyat sözleşmesinde bulunmayan
tek şey — **bir önceki işlem gününe göre değişim yüzdesi**.

NEDEN `get_current_prices`'a EKLENMEDİ: o sözleşme MCP tool'ları ve üç ajan
tarafından kullanılıyor; alan eklemek hepsinin çıktı şeklini değiştirir ve
docs/MCP-TOOLS.md'yi de kırar. Değişim yüzdesi yalnızca bu ekranın ihtiyacı,
dolayısıyla burada türetiliyor.

DEĞİŞİM NASIL HESAPLANIYOR: `get_asset_price_history` ile kısa bir pencere
(1 ay, günlük) çekilir ve serinin SON İKİ noktası kullanılır. "Dün"ün takvim
tarihi hesaplanmaz — piyasa hafta sonu ve tatilde kapalı, dolayısıyla önceki
işlem günü 1 ila 4 gün önce olabilir. Seride tek nokta varsa değişim `None`
döner; sıfır YAZILMAZ, "değişmedi" ile "hesaplanamadı" farklı şeylerdir
(CLAUDE.md "Uydurmama").
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import AssetClass, Granularity, TimeWindow
from app.core.exceptions import InsufficientDataError, NotFoundError
from app.schemas.market import (
    MarketIndicator,
    MarketIndicatorList,
    PortfolioInfluenceList,
    PortfolioInfluenceRow,
)
from app.services import portfolio_service, price_service

logger = logging.getLogger(__name__)

# Gösterge şeridindeki semboller ve sırası. Evrende (`providers/universe.py`)
# tanımlı olanlardan seçildi; XU100 fiyatlanıp saklanıyor çünkü kıyaslama
# zaten ona dayanıyor. Liste sabit: ekranın üst şeridi kullanıcıdan bağımsız
# bir "piyasa nabzı", portföye göre değişmemeli.
VARSAYILAN_GOSTERGELER: tuple[str, ...] = (
    "XU100",
    "USDTRY",
    "EURTRY",
    "XAUTRY",
    "XAGTRY",
    "BRENT",
    "SPX",
)

# Şeritteki gösterim sırası. `get_current_prices` çıktısının sırasına
# güvenilmiyor; ayrıca türetilmiş gösterge (EURUSD) o listede hiç yok.
# Burada olmayan bir sembol sona eklenir — çağıran kendi listesini
# verdiğinde (test, ileride kullanıcı seçimi) gösterge kaybolmasın.
SERIT_SIRASI: tuple[str, ...] = (
    "XU100",
    "USDTRY",
    "EURTRY",
    "EURUSD",
    "XAUTRY",
    "XAGTRY",
    "BRENT",
    "SPX",
)

# Para değeri OLMAYAN göstergeler: endeks puanı ve parite. Bunlarda
# `currency` `None` döner ve arayüz simgesiz basar — "₺11.284" BIST 100 için
# olmayan bir büyüklük iddiasıdır. Varlığın DB'deki `currency` alanı bu ayrımı
# yapamıyor: XU100 satırı TRY görünür.
BIRIMSIZ_SEMBOLLER: frozenset[str] = frozenset({"XU100", "SPX", "EURUSD"})

# Değişim hesabı için çekilen pencere. En kısa pencere (1 ay) yeterli: yalnızca
# son iki noktaya bakılıyor. Daha uzunu boşuna satır okur.
_DEGISIM_PENCERESI = TimeWindow.M1

# Etki listesinde gösterilecek en fazla pozisyon sayısı. Ağırlığa göre
# sıralanır; kart dar ve uzun listede kaydırma çubuğu tasarımı bozuyor.
_ETKI_SATIR_SINIRI = 6


def _degisim_yuzdesi(seri: list) -> Decimal | None:
    """Serinin son iki kapanışından yüzde değişim. İki nokta yoksa `None`."""
    if len(seri) < 2:
        return None
    onceki = seri[-2].close
    son = seri[-1].close
    if not onceki:
        # Sıfıra bölme: fiyat 0 olamaz ama sentetik/bozuk bir satır gelirse
        # cevabı düşürmek yerine değişimi hesaplanamadı sayıyoruz.
        return None
    return (son - onceki) / onceki * Decimal("100")


def gunluk_degisimler(db: Session, symbols: list[str]) -> dict[str, Decimal | None]:
    """`{sembol: değişim yüzdesi}`. Verisi olmayan sembol sözlükte YER ALMAZ.

    Fiyat geçmişi hiç yoksa (`make backfill` çalıştırılmamış) boş sözlük
    döner ve çağıran taraf değişimleri `None` gösterir — göstergelerin
    tamamının kaybolmasındansa fiyatı olup değişimi olmaması yeğdir.
    """
    if not symbols:
        return {}

    try:
        gecmis = price_service.get_asset_price_history(
            db,
            symbols,
            window=_DEGISIM_PENCERESI,
            granularity=Granularity.DAILY,
        )
    except InsufficientDataError:
        logger.info("market_service: degisim icin fiyat gecmisi yok (%s)", ",".join(symbols))
        return {}

    return {sembol: _degisim_yuzdesi(seri) for sembol, seri in gecmis.series.items()}


def _eur_usd(gostergeler: dict[str, MarketIndicator]) -> MarketIndicator | None:
    """EUR/USD paritesi: EUR/TRY ÷ USD/TRY.

    VERİTABANINA YAZILMIYOR ve yeni bir varlık değil — iki gerçek fiyatın
    oranı. `assets` tablosuna eklenseydi `derived_factor` (tek kaynaktan sabit
    çarpan) kalıbına uymazdı: burada iki ayrı kaynak var ve işlem bölme.

    Değişim yüzdesi de türetiliyor, yeniden sorgu YOK: EUR/TRY %e, USD/TRY %u
    değiştiyse oran (1+e)/(1+u) katına çıkar. Bu bir yaklaşım değil, tam
    eşitlik — iki serinin son iki noktası aynı iki güne aitse. İkisi de günlük
    kur serisi olduğu için takvimleri ortak; biri hesaplanamadıysa parite de
    hesaplanamamış sayılır (sıfır YAZILMAZ).

    Tarih ikisinin ESKİSİ, bayatlık ise biri bile bayatsa bayat: türetilmiş
    bir değer, girdilerinin en zayıfı kadar günceldir.
    """
    eur = gostergeler.get("EURTRY")
    usd = gostergeler.get("USDTRY")
    if eur is None or usd is None or not usd.price:
        return None

    oran = (eur.price / usd.price).quantize(Decimal("0.0001"))

    degisim: Decimal | None = None
    if eur.change_percent is not None and usd.change_percent is not None:
        usd_kat = Decimal(1) + usd.change_percent / Decimal(100)
        if usd_kat:
            eur_kat = Decimal(1) + eur.change_percent / Decimal(100)
            degisim = (eur_kat / usd_kat - Decimal(1)) * Decimal(100)

    return MarketIndicator(
        symbol="EURUSD",
        name="EUR/USD",
        asset_class=AssetClass.CURRENCY,
        price=oran,
        change_percent=degisim,
        price_date=min(eur.price_date, usd.price_date),
        # Kaynak "derived": rakam bir sağlayıcıdan gelmedi, iki fiyattan
        # hesaplandı. Kullanıcı fiyatın nereden geldiğini görebilmeli (AK 5.1).
        source="derived",
        stale=eur.stale or usd.stale,
        currency=None,
    )


def get_indicators(db: Session, symbols: list[str] | None = None) -> MarketIndicatorList:
    """Gösterge şeridi: güncel fiyat + bir önceki işlem gününe göre değişim.

    HİÇBİR SEMBOL TANINMAZSA HATA DEĞİL, BOŞ ŞERİT döner. `get_current_prices`
    bu durumda `NotFoundError` fırlatıyor — sohbet için doğru davranış
    ("sorduğun sembolü tanımıyorum"), ama burada sembolleri kullanıcı seçmiyor,
    sabit liste. Evren henüz seed'lenmemişse ya da bir sembol yeniden
    adlandırılmışsa tüm Piyasa ekranını düşürmek yerine şerit boş kalır ve
    eksikler `missing_symbols` ile bildirilir (AK 5.5: eksik veri sessizce
    yutulmaz ama cevabı da düşürmez).
    """
    istenen = list(symbols or VARSAYILAN_GOSTERGELER)
    try:
        fiyatlar = price_service.get_current_prices(db, istenen)
    except NotFoundError:
        logger.info("market_service: gosterge sembollerinin hicbiri taninmadi")
        return MarketIndicatorList(as_of=date.today(), indicators=[], missing_symbols=istenen)
    degisimler = gunluk_degisimler(db, [p.symbol for p in fiyatlar.prices])

    gostergeler = {
        p.symbol: MarketIndicator(
            symbol=p.symbol,
            name=p.name,
            asset_class=p.asset_class,
            price=p.price,
            change_percent=degisimler.get(p.symbol),
            price_date=p.price_date,
            source=p.source,
            stale=p.stale,
            currency=None if p.symbol in BIRIMSIZ_SEMBOLLER else p.currency,
        )
        for p in fiyatlar.prices
    }

    parite = _eur_usd(gostergeler)
    if parite is not None:
        gostergeler["EURUSD"] = parite

    sirali = [gostergeler[s] for s in SERIT_SIRASI if s in gostergeler]
    sirali += [g for s, g in gostergeler.items() if s not in SERIT_SIRASI]

    return MarketIndicatorList(
        as_of=fiyatlar.as_of,
        indicators=sirali,
        # İkisi birleştiriliyor: arayüz için ayrım anlamsız, ikisi de
        # "bu gösterge şeritte yok" demek.
        missing_symbols=[*fiyatlar.unknown_symbols, *fiyatlar.symbols_without_data],
    )


def portfoy_hisse_kodlari(db: Session, user_id: UUID, *, limit: int = 6) -> list[str]:
    """Kullanıcının HİSSE pozisyonlarının kodları, ağırlığa göre azalan.

    KAP takvimi şirket başına bir HTTP isteği demek (pykap toplu sorgu
    sunmuyor), bu yüzden liste dar tutuluyor. Yalnızca hisse: döviz, altın ve
    fonların KAP bildirimi yok.
    """
    degerleme = portfolio_service.get_holdings_valuation(db, user_id)
    hisseler = [h for h in degerleme.holdings if h.asset_class == AssetClass.STOCK]
    hisseler.sort(key=lambda h: h.weight_percent or Decimal("0"), reverse=True)
    return [h.symbol for h in hisseler[:limit]]


def get_portfolio_influence(db: Session, user_id: UUID) -> PortfolioInfluenceList:
    """Kullanıcının pozisyonları, ağırlık ve günlük değişimleriyle.

    Nakit HARİÇ: nakdin fiyatı ve dolayısıyla günlük değişimi yok, listede
    hep "—" olarak durur ve satır israfı olur.
    """
    degerleme = portfolio_service.get_holdings_valuation(db, user_id)

    pozisyonlar = [h for h in degerleme.holdings if h.asset_class != AssetClass.CASH]
    pozisyonlar.sort(key=lambda h: h.weight_percent or Decimal("0"), reverse=True)
    pozisyonlar = pozisyonlar[:_ETKI_SATIR_SINIRI]

    degisimler = gunluk_degisimler(db, [h.symbol for h in pozisyonlar])

    return PortfolioInfluenceList(
        as_of=degerleme.as_of,
        rows=[
            PortfolioInfluenceRow(
                symbol=h.symbol,
                name=h.name,
                asset_class=h.asset_class,
                weight_percent=h.weight_percent,
                change_percent=degisimler.get(h.symbol),
            )
            for h in pozisyonlar
        ],
    )
