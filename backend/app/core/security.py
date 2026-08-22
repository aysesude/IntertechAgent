"""Şifre özetleme ve JWT üretimi/çözümü.

Bu modül veritabanı ve HTTP bilmez — saf kriptografi. Kimin giriş yapabildiği
`services/auth_service.py`'de, isteğin kime ait olduğu `api/deps.py`'de
karara bağlanır.

Anahtar ve süreler `core/config.py`'den okunur; burada sabit yok.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import bcrypt
import jwt

from app.core.config import settings

# JWT'nin "kim" alanı (`sub`) her zaman kullanıcının UUID'sidir. E-posta ya da
# T.C. kimlik numarası KULLANILMAZ: ikisi de değişebilen, kişisel veri taşıyan
# alanlar; token'ın içine yazılırsa hem loglara sızar hem de değiştiklerinde
# geçerli token'lar sahipsiz kalır.
_SUBJECT_CLAIM = "sub"


class TokenError(Exception):
    """Token okunamadı: bozuk, imzası tutmuyor ya da süresi dolmuş.

    Sebep bilinçli olarak ayrıştırılmıyor — istemciye "süresi doldu" ile
    "imza geçersiz" arasındaki farkı söylemenin bir faydası yok, ikisinde de
    yapılacak şey aynı: yeniden giriş.
    """


def hash_password(password: str) -> str:
    """Şifreyi bcrypt ile özetler. Tuz (salt) her çağrıda yeniden üretilir,
    dolayısıyla aynı şifre her seferinde farklı bir özet verir."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    """Şifreyi özetle karşılaştırır.

    `password_hash` None olabilir: kimlik bilgisi atanmamış kullanıcılar
    (bkz. models/user.py) giriş yapamaz. Bu durumda bile bcrypt'e sahte bir
    doğrulama yaptırmıyoruz — zamanlama farkı üzerinden "bu TCKN kayıtlı mı"
    bilgisi sızabilir, ama `auth_service` zaten bulunan/bulunamayan ayrımını
    tek tip hatayla kapatıyor ve orada bir kukla özet doğrulanıyor.
    """
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Veritabanındaki değer geçerli bir bcrypt özeti değil (elle bozulmuş
        # ya da eski bir formattan kalmış). Çökmek yerine "eşleşmedi" say.
        return False


def create_access_token(user_id: UUID) -> tuple[str, int]:
    """Kullanıcı için imzalı bir erişim token'ı üretir.

    Döndürdüğü ikinci değer, token'ın kaç saniye geçerli olduğudur — istemci
    kendi süre hesabını yapmasın, sunucunun söylediğine uysun diye.
    """
    expires_in = settings.jwt_expire_minutes * 60
    now = datetime.now(UTC)
    payload = {
        _SUBJECT_CLAIM: str(user_id),
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str) -> UUID:
    """Token'ı doğrular ve içindeki kullanıcı UUID'sini döner.

    `jwt.decode` imzayı ve `exp`'i kendisi kontrol eder; algoritma listesi
    yapılandırmadan gelen TEK algoritmayla sınırlanır — açık liste
    bırakılırsa saldırgan `alg: none` ile imzasız token gönderebilir.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise TokenError("Oturum doğrulanamadı.") from exc

    subject = payload.get(_SUBJECT_CLAIM)
    if not subject:
        raise TokenError("Oturum doğrulanamadı.")
    try:
        return UUID(str(subject))
    except ValueError as exc:
        raise TokenError("Oturum doğrulanamadı.") from exc
