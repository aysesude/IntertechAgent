"""Giriş uçları (FR-0).

Kayıt (register), şifre değiştirme ve şifre sıfırlama uçları BİLEREK YOK:
demo kullanıcıları `make seed` ile üretilir. Arayüzdeki "Şifremi unuttum"
bağlantısının şu an bir karşılığı yoktur.

Çıkış (logout) ucu da yok ve gerekmiyor: token durumsuzdur (stateless),
sunucuda saklanmaz; çıkış, istemcinin token'ı silmesidir. Sunucu tarafında
iptal etmek bir kara liste (blacklist) tablosu gerektirirdi — 8 saatlik bir
demo token'ı için karşılığı olmayan bir karmaşıklık.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_current_user
from app.core.db import get_db
from app.core.exceptions import AuthenticationError
from app.core.security import create_access_token
from app.models import User
from app.schemas.auth import AuthUser, LoginRequest, TokenResponse
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """T.C. kimlik numarası + şifre ile giriş yapar, erişim token'ı döner.

    Hatalı kimlik ve hatalı şifre AYNI 401'i üretir; hangisinin yanlış olduğu
    söylenmez (bkz. `AuthenticationError`).
    """
    try:
        user = auth_service.authenticate(db, payload.national_id, payload.password)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.message,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    token, expires_in = create_access_token(user.id)
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=AuthUser(id=user.id, full_name=user.full_name, risk_profile=user.risk_profile),
    )


@router.get("/me", response_model=AuthUser)
def read_current_user(current_user: User = Depends(require_current_user)) -> AuthUser:
    """Elindeki token'ın hâlâ geçerli olup olmadığını ve kime ait olduğunu döner.

    Arayüz sayfa yenilendiğinde bunu çağırır: localStorage'daki token süresi
    dolmuşsa kullanıcıyı boş bir dashboard'a değil, doğrudan giriş ekranına
    düşürebilsin diye.
    """
    return AuthUser(
        id=current_user.id,
        full_name=current_user.full_name,
        risk_profile=current_user.risk_profile,
    )
