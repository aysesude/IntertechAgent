"""Piyasa ekranının uçları.

Üç uç, üç farklı kaynak:

- `/indicators` — `price_history` tablosu (günlük toplama işiyle dolar)
- `/headlines`  — BloombergHT son dakika akışı, İSTEK ANINDA canlı çekilir
- `/influence/{user_id}` — kullanıcının pozisyonları + günlük değişimleri

VERİ İZOLASYONU (AK 5.4): ilk ikisi kullanıcıya özel değil, yalnızca oturum
ister. Üçüncüsü portföy verisi taşıdığı için `verify_user_access` de ister.

CANLI UÇ NEDEN AJANDAN GEÇMİYOR: `/headlines` doğrudan sağlayıcıyı çağırır,
MCP tool'unu değil. Tool katmanı ajanların planlama arayüzü; bir ekran kartını
doldurmak için araya MCP çağrısı koymak yalnızca gecikme ve kırılganlık ekler.
Sağlayıcı ikisinde de aynı ve önbellek sağlayıcının içinde, dolayısıyla sohbet
ile ekran aynı 5 dakikalık önbelleği paylaşır.
"""

import functools
import logging
from uuid import UUID

import anyio.to_thread
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, verify_user_access
from app.core.db import get_db
from app.core.exceptions import NotFoundError
from app.models import User
from app.providers.base import ProviderError
from app.providers.bloomberg_ht_p import BloombergHtProvider
from app.providers.kap_p import KapProvider
from app.schemas.market import (
    MarketCalendarEntry,
    MarketCalendarList,
    MarketHeadline,
    MarketHeadlineList,
    MarketIndicatorList,
    PortfolioInfluenceList,
)
from app.services import market_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market", tags=["market"])

_KAYNAK_ADI = "BloombergHT"
_KAYNAK_URL = "https://www.bloomberght.com/sondakika"

_KAP_KAYNAK_ADI = "KAP"
_KAP_KAYNAK_URL = "https://www.kap.org.tr/tr"

# Ekranın haber kartı sekiz satır gösteriyor; fazlası kaydırma çubuğu açıyor.
_BASLIK_SINIRI = 8


@router.get("/indicators", response_model=MarketIndicatorList)
def read_market_indicators(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
) -> MarketIndicatorList:
    """Gösterge şeridi: BIST 100, USD/TRY, EUR/TRY, gram altın.

    Fiyatın tarihi ve kaynağı her satırda döner — fiyat "bugünün" fiyatı
    olmak zorunda değil (piyasa hafta sonu kapalı) ve arayüz bunu göstermek
    zorunda (AK 5.1, AK 5.3).
    """
    return market_service.get_indicators(db)


@router.get("/headlines", response_model=MarketHeadlineList)
async def read_market_headlines() -> MarketHeadlineList:
    """Genel piyasa gündemi — istek anında BloombergHT'den canlı çekilir.

    Başlıklar sitenin kendi ifadesiyle döner; özet, etki seviyesi veya
    kaynak sayısı ÜRETİLMEZ (bkz. app/schemas/market.py).

    Kaynağa ulaşılamazsa 503 döner. Boş liste dönmek "bugün haber yok" gibi
    okunurdu; ulaşılamamak ile haber olmaması aynı şey değil (AK 5.5).
    """
    provider = BloombergHtProvider()
    cagri = functools.partial(provider.fetch_latest_headlines, _BASLIK_SINIRI)
    try:
        basliklar = await anyio.to_thread.run_sync(cagri, abandon_on_cancel=True)
    except ProviderError as exc:
        logger.warning("read_market_headlines: saglayici hatasi — %s", exc)
        raise HTTPException(status_code=503, detail="Piyasa gündemine şu an ulaşılamıyor.") from exc

    return MarketHeadlineList(
        headlines=[MarketHeadline(title=b.baslik, published_at=b.tarih) for b in basliklar],
        source_name=_KAYNAK_ADI,
        source_url=_KAYNAK_URL,
    )


@router.get("/influence/{user_id}", response_model=PortfolioInfluenceList)
def read_portfolio_influence(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
) -> PortfolioInfluenceList:
    """Kullanıcının en ağırlıklı pozisyonları ve günlük değişimleri.

    Piyasa hareketinin portföye nereden dokunduğunu gösterir; nakit hariç
    tutulur (fiyatı ve dolayısıyla değişimi yok).
    """
    verify_user_access(user_id, current_user)
    try:
        return market_service.get_portfolio_influence(db, user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc


@router.get("/calendar/{user_id}", response_model=MarketCalendarList)
async def read_market_calendar(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
) -> MarketCalendarList:
    """Kullanıcının hisselerinin YAKLAŞAN KAP bildirim takvimi.

    Makro takvim (TCMB PPK, TÜİK, ABD TÜFE) DEĞİLDİR: onun doğrulanmış bir
    kaynağı elimizde yok. KAP'ın kendi yayımladığı dosyalama takvimi ise
    resmî ve kullanıcının portföyüne doğrudan bağlı.

    Her kayıt tek bir tarih değil bir PENCERE taşır; `due_date` aralığın
    sonudur ve kullanıcı için bağlayıcı olan gün odur.

    Boş liste HATA DEĞİLDİR: kullanıcının hissesi olmayabilir ya da yakın
    dönemde beklenen bildirim bulunmayabilir.
    """
    verify_user_access(user_id, current_user)
    try:
        kodlar = market_service.portfoy_hisse_kodlari(db, user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc

    kayitlar = []
    if kodlar:
        cagri = functools.partial(KapProvider().fetch_expected_disclosures, kodlar)
        try:
            kayitlar = await anyio.to_thread.run_sync(cagri, abandon_on_cancel=True)
        except ProviderError as exc:
            logger.warning("read_market_calendar: saglayici hatasi — %s", exc)
            raise HTTPException(
                status_code=503, detail="Bildirim takvimine şu an ulaşılamıyor."
            ) from exc

    return MarketCalendarList(
        entries=[
            MarketCalendarEntry(
                symbol=k.ticker,
                company=k.sirket,
                subject=k.konu,
                period=k.donem,
                start_date=k.baslangic,
                due_date=k.son_tarih,
            )
            for k in kayitlar
        ],
        source_name=_KAP_KAYNAK_ADI,
        source_url=_KAP_KAYNAK_URL,
    )
