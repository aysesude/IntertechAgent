"""Uçların ortak bağımlılıkları: "istek kime ait" ve "bu kaynağa erişebilir mi".

AK 5.4 ("kullanıcıya özel finansal veriler yalnızca ilgili kullanıcı
tarafından erişilebilir") tek bir yerde uygulanır. Uçlar iki satır ekler:

    current_user: User = Depends(get_current_user)   # yoksa 401
    verify_user_access(user_id, current_user)         # başkasınınsa 403

Yol imzaları (`/api/portfolio/{user_id}`) BİLEREK DEĞİŞTİRİLMEDİ. `/me`
kalıbına geçmek MCP tool'larını, ajanları, testleri ve docs/API.md'yi
topluca kırardı; kazancı ise yalnızca estetik olurdu — kimliğin kaynağı zaten
token, yoldaki değer artık yalnızca doğrulanan bir iddia.
"""

from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.exceptions import AuthenticationError
from app.core.security import TokenError, decode_access_token
from app.models import User
from app.services import auth_service

# auto_error=False: başlık yokken FastAPI'nin kendi 403'ünü üretmesini
# istemiyoruz. Eksik token 401'dir (kimlik yok), 403 değil (kimlik var ama
# yetki yok) — arayüz ikisini farklı ele alıyor: 401 → giriş ekranı,
# 403 → "bu veriye erişiminiz yok".
_bearer_scheme = HTTPBearer(auto_error=False)

# 401 yanıtlarında bulunması gereken standart başlık (RFC 6750).
_UNAUTHENTICATED_HEADERS = {"WWW-Authenticate": "Bearer"}


def _unauthenticated(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers=_UNAUTHENTICATED_HEADERS,
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """İstekteki Bearer token'dan kullanıcıyı çözer.

    `AUTH_ENFORCE=false` iken token YOKSA `None` döner ve istek geçer — token
    VARSA yine de doğrulanır (bozuk token sessizce yok sayılmaz). Bu yalnızca
    geçiş dönemi içindir: token göndermeyen eski `frontend/` çalışmaya devam
    etsin diye. Bayrağın varsayılanı `True`, yani unutulursa auth açık kalır.
    """
    if credentials is None:
        if not settings.auth_enforce:
            return None
        raise _unauthenticated("Bu işlem için giriş yapmalısınız.")

    try:
        user_id = decode_access_token(credentials.credentials)
        return auth_service.get_user_by_id(db, user_id)
    except (TokenError, AuthenticationError) as exc:
        raise _unauthenticated(exc.message if isinstance(exc, AuthenticationError) else str(exc))


def require_current_user(current_user: User | None = Depends(get_current_user)) -> User:
    """Kimliği zorunlu kılar — `AUTH_ENFORCE` kapalı olsa bile.

    Kullanıcının kendi bilgisini döndüren uçlar (`/api/auth/me`) için: orada
    "kimliksiz devam et" diye bir davranış yok, cevaplanacak bir soru da yok.
    """
    if current_user is None:
        raise _unauthenticated("Bu işlem için giriş yapmalısınız.")
    return current_user


def verify_user_access(user_id: UUID, current_user: User | None) -> None:
    """Yoldaki/gövdedeki `user_id` gerçekten isteği yapan kullanıcı mı (AK 5.4).

    `current_user` None ise (yalnızca AUTH_ENFORCE=false iken mümkün) kontrol
    atlanır — geçiş dönemi davranışı, bkz. `get_current_user`.

    403 döner, 404 değil: "başkasının portföyü" ile "olmayan portföy" farklı
    şeylerdir ve 404'e çevirmek hata ayıklamayı zorlaştırır. Kaynağın var olup
    olmadığı bilgisi burada zaten sızmıyor — kontrol veritabanına hiç
    bakmadan, yalnızca iki UUID karşılaştırılarak yapılıyor.
    """
    if current_user is None:
        return
    if user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu veriye erişim yetkiniz yok.",
        )
