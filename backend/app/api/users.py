"""Kullanıcı risk profili uçları (anket ekranının yazdığı yer).

Diğer uçlar gibi ajan/LLM çağırmaz, servisi doğrudan çağırır. Hata çevirimi
`portfolio.py` ile aynı desende: servis `AppError` türevi fırlatır, burada
HTTP durum koduna çevrilir. Servisler HTTP bilmez, uçlar SQL bilmez.

Bu dosya projedeki tek YAZAN HTTP ucunu içerir; geri kalan her uç salt okur.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import NotFoundError, ValidationAppError
from app.schemas.user import RiskProfileUpdate, UserRiskProfile
from app.services.user_service import get_user_risk_profile, set_user_risk_profile

router = APIRouter(prefix="/api/users", tags=["users"])

_STATUS_BY_ERROR = {
    NotFoundError: 404,
    ValidationAppError: 422,
}

APP_ERRORS = tuple(_STATUS_BY_ERROR)


def _http(exc: Exception) -> HTTPException:
    for error_type, status_code in _STATUS_BY_ERROR.items():
        if isinstance(exc, error_type):
            return HTTPException(status_code=status_code, detail=exc.message)
    raise exc


@router.get("/{user_id}/risk-profile", response_model=UserRiskProfile)
def read_risk_profile(user_id: UUID, db: Session = Depends(get_db)) -> UserRiskProfile:
    """Kullanıcının kayıtlı risk profili + seçilebilir profillerin listesi.

    `available_profiles` arayüzün anket seçeneklerini kendi tarafında sabit
    yazmaması içindir; kademe sayısı değişirse arayüz kod değişikliği
    olmadan yeni seçenekleri görür.
    """
    try:
        return get_user_risk_profile(db, user_id)
    except APP_ERRORS as exc:
        raise _http(exc) from exc


@router.put("/{user_id}/risk-profile", response_model=UserRiskProfile)
def update_risk_profile(
    user_id: UUID,
    payload: RiskProfileUpdate,
    db: Session = Depends(get_db),
) -> UserRiskProfile:
    """Anket sonucunu kaydeder (Not 1/Not 4: profili kullanıcı bildirir).

    PUT seçildi çünkü işlem idempotenttir: aynı sonucu tekrar göndermek
    kullanıcı için hata değil, aynı duruma yeniden ulaşmaktır.

    Tanınmayan bir profil değeri FastAPI/Pydantic tarafından 422 ile
    reddedilir; burada ikinci bir doğrulama YOK — aynı hata için iki farklı
    mesaj üretmemek için (bkz. portfolio.py'deki tarih ayrıştırma notu).
    """
    try:
        return set_user_risk_profile(db, user_id, payload.risk_profile)
    except APP_ERRORS as exc:
        raise _http(exc) from exc
