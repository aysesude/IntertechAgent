"""Al/Sat uçları — projedeki ilk PARA HAREKET ETTİREN yüzey.

Şimdiye kadarki tek yazan uç risk profiliydi ve bir beyanı güncelliyordu;
buradaki her POST defterin kendisine kayıt düşüyor. Hata çevirimi diğer
uçlarla aynı desende: servis `AppError` türevi fırlatır, burada HTTP durum
koduna çevrilir. Servisler HTTP bilmez, uçlar SQL bilmez.

Fiyat İSTEK GÖVDESİNDE ALINMAZ. İstemciye fiyat yazdırmak, tarayıcı
üzerinden istenen fiyattan alım yapmaya açık kapı bırakırdı; fiyat her zaman
sunucudaki son kapanıştan okunur.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, verify_user_access
from app.core.db import get_db
from app.core.exceptions import NotFoundError, ValidationAppError
from app.models import User
from app.schemas.trade import (
    DepositRequest,
    TradableList,
    TradePreview,
    TradeRequest,
    TradeResult,
)
from app.services.ledger_service import LedgerError
from app.services.trade_service import (
    deposit_cash,
    execute_trade,
    get_tradable_assets,
    preview_trade,
)

router = APIRouter(prefix="/api/trade", tags=["trade"])

_STATUS_BY_ERROR = {
    NotFoundError: 404,
    ValidationAppError: 422,
    # Defter kuralı ihlali (yetersiz nakit, fazla satış) kullanıcının
    # düzeltebileceği bir durumdur, sunucu hatası değil.
    LedgerError: 422,
}

APP_ERRORS = tuple(_STATUS_BY_ERROR)


def _http(exc: Exception) -> HTTPException:
    for error_type, status_code in _STATUS_BY_ERROR.items():
        if isinstance(exc, error_type):
            return HTTPException(status_code=status_code, detail=str(exc))
    raise exc


@router.get("/{user_id}/assets", response_model=TradableList)
def read_tradable_assets(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
) -> TradableList:
    """Al/Sat ekranının listesi: varlıklar, fiyatlar, uygunluk, eldeki miktar.

    Uygun olmayan varlıklar listeden DÜŞMEZ, `can_buy=false` ve
    `block_reason` ile döner — kilidin sebebini göstermek, kullanıcının
    hatayı kendinde aramasını engelliyor.
    """
    verify_user_access(user_id, current_user)
    try:
        return get_tradable_assets(db, user_id)
    except APP_ERRORS as exc:
        raise _http(exc) from exc


@router.post("/{user_id}/preview", response_model=TradePreview)
def preview(
    user_id: UUID,
    payload: TradeRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
) -> TradePreview:
    """Emri hesaplar, DEFTERE YAZMAZ.

    POST, çünkü gövde alıyor — yan etkisi yok. Kullanıcı "ne ödeyeceğim,
    bakiyem ne olacak" sorusunu onaylamadan önce görmeli.
    """
    verify_user_access(user_id, current_user)
    try:
        return preview_trade(db, user_id, payload.symbol, payload.side, payload.quantity)
    except APP_ERRORS as exc:
        raise _http(exc) from exc


@router.post("/{user_id}/execute", response_model=TradeResult)
def execute(
    user_id: UUID,
    payload: TradeRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
) -> TradeResult:
    """Emri deftere yazar.

    Başkasının portföyünde işlem yapabilmek, bu projedeki en ağır yetki
    ihlali olurdu — `verify_user_access` burada AK 5.4'ten fazlasını koruyor.
    """
    verify_user_access(user_id, current_user)
    try:
        return execute_trade(db, user_id, payload.symbol, payload.side, payload.quantity)
    except APP_ERRORS as exc:
        raise _http(exc) from exc


@router.post("/{user_id}/deposit")
def deposit(
    user_id: UUID,
    payload: DepositRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
) -> dict:
    """Demo nakit yatırma.

    GERÇEK BİR ÖDEME AKIŞI DEĞİLDİR; bakiyesi biten kullanıcının demo
    akışında kilitlenmemesi için var. Arayüz bunu böyle sunmalı.
    """
    verify_user_access(user_id, current_user)
    try:
        return {"cash_balance": deposit_cash(db, user_id, payload.amount)}
    except APP_ERRORS as exc:
        raise _http(exc) from exc
