"""Dashboard'un okuduğu portföy uçları.

Bu uçlar AJANLARI ÇAĞIRMAZ, servisleri doğrudan çağırır (Diyagram 01/03).
Sebep: dashboard açılışında sorulmuş bir soru ve anlatılacak bir şey yok —
araya LLM koymak, ekranı model hızına bağlar ve halüsinasyon yüzeyi açar.
Ajanlar yalnızca sohbet yolunda (`POST /api/chat`) devrededir.

Hata çevirimi tek yerde: servis katmanı `AppError` türevleri fırlatır, burada
HTTP durum koduna çevrilir. Servisler HTTP bilmez, uçlar SQL bilmez.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, verify_user_access
from app.core.config import Granularity, PriceCurrency, TimeWindow
from app.core.db import get_db
from app.core.exceptions import InsufficientDataError, NotFoundError, ValidationAppError
from app.models import User
from app.schemas.portfolio import (
    BenchmarkComparison,
    HoldingsValuation,
    PerformanceResult,
    PortfolioSummary,
    PriceHistoryResult,
    TransactionList,
)
from app.services import price_service
from app.services.portfolio_service import (
    get_benchmark_comparison,
    get_holdings_valuation,
    get_portfolio_performance,
    get_portfolio_summary,
    get_transactions,
)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

# Fiyat serisi portföyden bağımsız (kullanıcı gerektirmez) ama arayüzde portföy
# ekranının bir parçası; kendi ön ekinde duruyor ki ileride önbelleklenirken
# kullanıcı bazlı uçlarla karışmasın.
price_router = APIRouter(prefix="/api/prices", tags=["prices"])


_STATUS_BY_ERROR = {
    NotFoundError: 404,
    ValidationAppError: 422,
    InsufficientDataError: 409,
}

APP_ERRORS = tuple(_STATUS_BY_ERROR)


def _http(exc: Exception) -> HTTPException:
    """Uygulama hatasını HTTP karşılığına çevirir.

    404 "kullanıcı/portföy yok", 422 "istek hatalı", 409 "veri yetersiz".
    Yetersiz veri 404 DEĞİL: kaynak var, hesaplanacak veri yok — arayüz bu ikisini
    farklı göstermeli ("kullanıcı bulunamadı" ile "bu dönemde veri yok" aynı şey
    değil).
    """
    for error_type, status_code in _STATUS_BY_ERROR.items():
        if isinstance(exc, error_type):
            return HTTPException(status_code=status_code, detail=exc.message)
    raise exc


@router.get("/{user_id}", response_model=PortfolioSummary)
def read_portfolio_summary(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
) -> PortfolioSummary:
    """Toplam değer, maliyet, kâr/zarar ve varlık sınıfı dağılımı (pasta grafiği)."""
    verify_user_access(user_id, current_user)
    try:
        return get_portfolio_summary(db, user_id)
    except APP_ERRORS as exc:
        raise _http(exc) from exc


@router.get("/{user_id}/holdings", response_model=HoldingsValuation)
def read_holdings(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
) -> HoldingsValuation:
    """Varlık tablosu: TRY değer, ağırlık, ortalama maliyet, gerçekleşmiş/gerçekleşmemiş K/Z.

    Fiyatı bulunamayan varlık listeden düşmez; `price_missing=True` ile döner ve
    arayüz o satırda "—" gösterir.
    """
    verify_user_access(user_id, current_user)
    try:
        return get_holdings_valuation(db, user_id)
    except APP_ERRORS as exc:
        raise _http(exc) from exc


@router.get("/{user_id}/performance", response_model=PerformanceResult)
def read_performance(
    user_id: UUID,
    window: TimeWindow = Query(TimeWindow.M1, description="1m | 3m | 6m | 12m | ytd"),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
) -> PerformanceResult:
    """Değer serisi + kümülatif yatırılan para (aradaki boşluk toplam kârdır).

    `summary.change_amount` ve `change_percent` dış akıştan arındırılmıştır:
    para yatırmak "kâr" olarak görünmez.
    """
    verify_user_access(user_id, current_user)
    try:
        return get_portfolio_performance(db, user_id, window)
    except APP_ERRORS as exc:
        raise _http(exc) from exc


@router.get("/{user_id}/transactions", response_model=TransactionList)
def read_transactions(
    user_id: UUID,
    start_date: date | None = Query(None, description="YYYY-AA-GG, dahil"),
    end_date: date | None = Query(None, description="YYYY-AA-GG, dahil"),
    symbols: list[str] | None = Query(None, description="Yalnızca bu semboller"),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
) -> TransactionList:
    """Alım/satım işaretçileri ve nakit hareketleri.

    `position_after` işlemden sonraki toplam pozisyondur; tarih süzgeci
    uygulansa bile defterin başından sayılır.
    """
    # Tarih ayrıştırma FastAPI'ye bırakılır: bozuk biçim zaten 422 döner,
    # burada ikinci bir doğrulama yazmak iki farklı hata mesajı üretirdi.
    verify_user_access(user_id, current_user)
    try:
        return get_transactions(
            db, user_id, start_date=start_date, end_date=end_date, symbols=symbols
        )
    except APP_ERRORS as exc:
        raise _http(exc) from exc


@router.get("/{user_id}/benchmark", response_model=BenchmarkComparison)
def read_benchmark(
    user_id: UUID,
    window: TimeWindow = Query(TimeWindow.M3, description="1m | 3m | 6m | 12m | ytd"),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
) -> BenchmarkComparison:
    """Portföy getirisi ↔ endeksler (bar grafiği).

    Pencere başındaki miktarlar dondurulur, yalnızca fiyat değişimi ölçülür —
    endeksin saf fiyat getirisiyle aynı ölçekte olması için.
    """
    verify_user_access(user_id, current_user)
    try:
        return get_benchmark_comparison(db, user_id, window)
    except APP_ERRORS as exc:
        raise _http(exc) from exc


@price_router.get("/history", response_model=PriceHistoryResult)
def read_price_history(
    symbols: list[str] = Query(..., description="Sembol listesi, ör. symbols=TUPRS&symbols=XAUTRY"),
    window: TimeWindow = Query(TimeWindow.M3),
    granularity: Granularity = Query(Granularity.AUTO),
    currency: PriceCurrency = Query(PriceCurrency.TRY),
    db: Session = Depends(get_db),
    # Kullanıcıya özel veri DEĞİL: aynı sembolün serisi herkes için aynı,
    # bu yüzden sahiplik kontrolü yok. Yine de giriş şartı aranıyor — tek
    # açık uç bırakmak, evrendeki tüm sembollerin fiyat geçmişini kimliksiz
    # dışarı vermek olurdu.
    current_user: User | None = Depends(get_current_user),  # noqa: ARG001
) -> PriceHistoryResult:
    """Sembol bazlı kapanış serisi (varlık başına fiyat grafiği).

    CANLI FİYAT DEĞİLDİR: veriler günlük toplama işiyle yazılır, bu uç internete
    çıkmaz. `as_of` verinin hangi güne ait olduğunu bildirir.

    Kısmi veri hata değildir: bir sembolün verisi yoksa diğerlerinin serisi yine
    döner, eksik olan `symbols_without_data` ile bildirilir.
    """
    try:
        return price_service.get_asset_price_history(
            db, symbols, window=window, granularity=granularity, currency=currency
        )
    except APP_ERRORS as exc:
        raise _http(exc) from exc
