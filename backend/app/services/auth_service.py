"""Giriş doğrulama (FR-0).

`user_service.py` gibi bu da dar bir yazma kapısıdır: yalnızca `last_login_at`
alanını günceller. Kayıt (register), şifre değiştirme ve şifre sıfırlama
BİLEREK YOK — demo kullanıcıları `make seed` ile üretilir, kendi kimliklerini
değiştiremezler.

NEDEN AJANA AÇILMIYOR. `user_service`'teki gerekçenin aynısı, daha da güçlü
hâli: bu fonksiyonlar için MCP tool'u yazılmadı ve yazılmamalı. Sohbet
üzerinden bir modelin kimlik doğrulama yapabilmesi, prompt enjeksiyonuyla
("şu kullanıcı olarak giriş yap") oturum ele geçirilmesi demek olurdu.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError
from app.core.security import hash_password, verify_password
from app.models import User

# Kayıtlı olmayan bir T.C. kimlik numarası denendiğinde bcrypt'e doğrulatılan
# kukla özet. Amacı: "kullanıcı yok" dalının "şifre yanlış" dalından belirgin
# biçimde HIZLI dönmesini engellemek. Aksi halde yanıt süresi ölçülerek hangi
# numaraların sistemde kayıtlı olduğu çıkarılabilirdi (zamanlama sızıntısı).
# Modül yüklenirken bir kez hesaplanır.
_DUMMY_HASH = hash_password("zamanlama-sizintisina-karsi-kukla-deger")

# Kimlik ya da şifre hatalı — ikisi için de AYNI metin (bkz. AuthenticationError).
_INVALID_CREDENTIALS = "T.C. kimlik numarası veya şifre hatalı."


def authenticate(db: Session, national_id: str, password: str) -> User:
    """Kimlik bilgilerini doğrular ve kullanıcıyı döner.

    Başarılı girişte `last_login_at` güncellenir. Hiçbir durumda hangi alanın
    yanlış olduğu söylenmez.
    """
    user = db.execute(select(User).where(User.national_id == national_id)).scalar_one_or_none()

    if user is None:
        # Kullanıcı yok. Yine de bir doğrulama yapıp aynı süreyi harcıyoruz.
        verify_password(password, _DUMMY_HASH)
        raise AuthenticationError(_INVALID_CREDENTIALS)

    # `password_hash` None ise (kimlik bilgisi atanmamış kullanıcı, bkz.
    # models/user.py) verify_password False döner — giriş yapılamaz.
    if not verify_password(password, user.password_hash):
        raise AuthenticationError(_INVALID_CREDENTIALS)

    user.last_login_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return user


def get_user_by_id(db: Session, user_id: UUID) -> User:
    """Token'daki kimliğe karşılık gelen kullanıcıyı döner.

    Kullanıcı silinmişse token hâlâ imza olarak geçerlidir ama sahibi yoktur;
    bu bir yetkilendirme sorunu değil, kimlik sorunudur — 401 üretilir ki
    istemci yeniden giriş yapsın.
    """
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise AuthenticationError("Oturum doğrulanamadı.")
    return user
