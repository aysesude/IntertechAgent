"""Giriş uçları (FR-0).

Kayıt (register) ucu BİLEREK YOK: demo kullanıcıları `make seed` ile üretilir.

Şifre yenileme uçları DEMO akışıdır: e-posta gönderilmez, kod sunucuda
üretilmez ve saklanmaz (yapılandırmadaki sabit kod kabul edilir), ama şifre
GERÇEKTEN güncellenir. Güvenlik sınırı ve kapatma yolu için bkz.
`Settings.demo_password_reset_enabled`.

Çıkış (logout) ucu da yok ve gerekmiyor: token durumsuzdur (stateless),
sunucuda saklanmaz; çıkış, istemcinin token'ı silmesidir. Sunucu tarafında
iptal etmek bir kara liste (blacklist) tablosu gerektirirdi — 8 saatlik bir
demo token'ı için karşılığı olmayan bir karmaşıklık.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_current_user
from app.core.config import settings
from app.core.db import get_db
from app.core.exceptions import AuthenticationError, ValidationAppError
from app.core.security import create_access_token
from app.models import User
from app.schemas.auth import (
    AuthUser,
    LoginRequest,
    PasswordResetComplete,
    PasswordResetInfo,
    PasswordResetRequest,
    TokenResponse,
)
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


@router.post("/password-reset/request", response_model=PasswordResetInfo)
def request_password_reset(payload: PasswordResetRequest) -> PasswordResetInfo:
    """Yenileme akışını başlatır.

    Kimliğin kayıtlı olup olmadığına BAKMADAN aynı yanıtı döner — aksi halde
    bu uç, hangi T.C. kimlik numaralarının sistemde olduğunu tek tek denemeye
    açık bir araca dönüşürdü.

    E-posta GÖNDERİLMEZ (demo). Yanıt yalnızca arayüzün alan uzunluğunu ve
    geri sayımı sabit yazmaması için bu iki değeri taşır.
    """
    if not settings.demo_password_reset_enabled:
        raise HTTPException(status_code=404, detail="Şifre yenileme bu ortamda kapalı.")
    return PasswordResetInfo(
        code_length=len(settings.demo_reset_code),
        expires_in_seconds=settings.password_reset_code_ttl_seconds,
    )


@router.post("/password-reset/complete", status_code=204)
def complete_password_reset(payload: PasswordResetComplete, db: Session = Depends(get_db)) -> None:
    """Doğrulama kodunu kontrol eder ve şifreyi günceller.

    Hatalı kimlik ile hatalı kod AYNI 401'i döner. Başarıda gövde yok (204):
    dönecek bir veri yok, arayüz kullanıcıyı giriş ekranına alır.
    """
    try:
        auth_service.reset_password(db, payload.national_id, payload.code, payload.new_password)
    except ValidationAppError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=exc.message) from exc
