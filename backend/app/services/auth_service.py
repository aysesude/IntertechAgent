"""Giriş doğrulama ve kayıt (FR-0).

`user_service.py` gibi bu da dar bir yazma kapısıdır: kullanıcı oluşturma,
`last_login_at` ve şifre yenileme. Başka hiçbir yol `users` tablosuna yazmaz.

NEDEN AJANA AÇILMIYOR. `user_service`'teki gerekçenin aynısı, daha da güçlü
hâli: bu fonksiyonlar için MCP tool'u yazılmadı ve yazılmamalı. Sohbet
üzerinden bir modelin kimlik doğrulama ya da hesap açma yapabilmesi, prompt
enjeksiyonuyla ("şu kullanıcı olarak giriş yap") oturum ele geçirilmesi
demek olurdu.

"""

import secrets
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import risk_profile_for_survey_score, settings
from app.core.exceptions import AuthenticationError, ValidationAppError
from app.core.security import hash_password, verify_password
from app.models import Portfolio, TransactionType, User
from app.services.ledger_service import record_transaction

# Kayıtlı olmayan bir T.C. kimlik numarası denendiğinde bcrypt'e doğrulatılan
# kukla özet. Amacı: "kullanıcı yok" dalının "şifre yanlış" dalından belirgin
# biçimde HIZLI dönmesini engellemek. Aksi halde yanıt süresi ölçülerek hangi
# numaraların sistemde kayıtlı olduğu çıkarılabilirdi (zamanlama sızıntısı).
# Modül yüklenirken bir kez hesaplanır.
_DUMMY_HASH = hash_password("zamanlama-sizintisina-karsi-kukla-deger")

# Kimlik ya da şifre hatalı — ikisi için de AYNI metin (bkz. AuthenticationError).
_INVALID_CREDENTIALS = "T.C. kimlik numarası veya şifre hatalı."


# Hangi alanın çakıştığı SÖYLENMEZ: "bu T.C. kimlik numarası kayıtlı" demek,
# numaraları tek tek deneyerek kimin müşteri olduğunu öğrenmeye açık bir araç
# yaratırdı (giriş ucundaki aynı gerekçe).
_CAKISMA_MESAJI = "Bu bilgilerle bir hesap zaten var."


def _cakisan_kullanici(db: Session, national_id: str, email: str) -> User | None:
    """T.C. numarası ya da e-postası çakışan İLK kullanıcı.

    `.first()`, `.scalar_one_or_none()` DEĞİL: numara bir kullanıcıya,
    e-posta başka bir kullanıcıya aitse sorgu İKİ satır döner ve
    `scalar_one_or_none` `MultipleResultsFound` fırlatırdı — kullanıcı 409
    yerine 500 görürdü. Kaç tanesinin çakıştığı zaten önemli değil; biri bile
    varsa kayıt olmaz.

    E-posta KÜÇÜK HARFE İNDİRİLEREK karşılaştırılır. `String` sütununda UNIQUE
    kısıt harf duyarlıdır, yani "Ayse@x.com" ile "ayse@x.com" veritabanı için
    iki farklı değerdir ve aynı kişi iki hesap açabilirdi.
    """
    return (
        db.execute(
            select(User).where(
                (User.national_id == national_id) | (func.lower(User.email) == email.lower())
            )
        )
        .scalars()
        .first()
    )


def register(
    db: Session,
    *,
    full_name: str,
    national_id: str,
    email: str,
    password: str,
    survey_score: int | None,
    initial_deposit_try: Decimal,
) -> User:
    """Yeni kullanıcı, portföyü ve açılış bakiyesiyle birlikte oluşturur.

    ÜÇÜ TEK İŞLEMDE: kullanıcı, portföy ve açılış yatırımı. Ayrı ayrı
    yazılsaydı arada bir hata portföysüz bir kullanıcı ya da parasız bir
    portföy bırakırdı; ikisi de sistemin hiçbir yerinde beklenmeyen durumlar.
    Commit çağıran uca (uç fonksiyonu) bırakılıyor, mevcut servis kalıbıyla
    aynı.

    AÇILIŞ BAKİYESİ DEFTERE YAZILIR. "Başka bankadan getirilen" tutar
    `record_transaction(DEPOSIT)` ile kaydedilir — nakit bakiyeyi doğrudan
    bir alana yazmak defterin tek gerçeklik kaynağı olması kuralını bozardı
    ve portföy değeri işlemlerden yeniden üretilemez hâle gelirdi
    (docs/DATA.md altın kural). Tutar 0 ise işlem HİÇ yazılmaz: sıfırlık bir
    yatırım kaydı defteri kirletir.

    `survey_score` `None` OLABİLİR: anket kayıt akışından çıkarılıp ilk
    girişe taşındı. O durumda `risk_survey_score` boş kalır ve `risk_profile`
    modelin varsayılanında (Dengeli) durur — uygunluk kontrolü puanın
    yokluğunu zaten görüyor ve tavsiye katmanını kapatıyor. Varsayılan
    profili "ölçülmüş" gibi sunmuyoruz; arayüz kullanıcıyı ankete alıyor.

    Puan verildiğinde `risk_profile` ondan TÜRETİLİR, ayrıca sorulmaz — iki
    ölçeğin ayrışmaması için tek kaynak `risk_survey_score`.
    """
    if _cakisan_kullanici(db, national_id, email) is not None:
        raise ValidationAppError(_CAKISMA_MESAJI)

    if initial_deposit_try < 0:
        raise ValidationAppError("Aktarılacak tutar negatif olamaz.")

    user = User(
        email=email,
        full_name=full_name,
        national_id=national_id,
        password_hash=hash_password(password),
        risk_survey_score=survey_score,
    )
    if survey_score is not None:
        user.risk_profile = risk_profile_for_survey_score(survey_score)
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        # SON SÖZÜ VERİTABANI SÖYLER. Yukarıdaki kontrol sorgusu ile bu yazma
        # arasında başka bir istek aynı T.C. numarasını ya da e-postayı almış
        # olabilir; iki istek de kontrolü geçer, biri yazar, diğeri buraya
        # düşer. Yakalanmasaydı kullanıcı 409 yerine 500 görürdü — üstelik
        # "kayıt olamadım, sistem bozuk" diye tekrar tekrar denerdi.
        #
        # Tek koruma olarak kontrol sorgusuna güvenilemez; `users.national_id`
        # ve `users.email` üzerindeki UNIQUE kısıtlar asıl güvencedir.
        db.rollback()
        raise ValidationAppError(_CAKISMA_MESAJI) from exc

    portfolio = Portfolio(user_id=user.id)
    db.add(portfolio)
    db.flush()

    if initial_deposit_try > 0:
        record_transaction(
            db,
            portfolio.id,
            TransactionType.DEPOSIT,
            transaction_date=datetime.now(UTC),
            cash_amount_try=initial_deposit_try,
            note="Açılış aktarımı",
        )

    return user


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


# Yenileme hatalarında tek tip mesaj: hangi alanın yanlış olduğunu söylemek,
# "bu kimlik kayıtlı mı" sorusuna dolaylı cevap verirdi (giriş ucundaki
# gerekçenin aynısı).
_INVALID_RESET = "T.C. kimlik numarası veya doğrulama kodu hatalı."


def reset_password(db: Session, national_id: str, code: str, new_password: str) -> None:
    """Şifreyi günceller (DEMO akışı).

    TEMSİLİ OLAN: kod sunucuda üretilmiyor ve saklanmıyor; yapılandırmadaki
    sabit kod kabul ediliyor, e-posta gönderilmiyor.
    GERÇEK OLAN: şifre bcrypt ile özetlenip veritabanına YAZILIYOR, yani
    kullanıcı bundan sonra yeni şifresiyle giriş yapar.

    Bilinen sınır: yenileme sonrası ESKİ TOKEN'LAR geçersizleşmez. Bunun için
    token kara listesi ya da özete bağlı bir doğrulama gerekir; 8 saatlik demo
    token'ı için karşılığı olmayan bir karmaşıklık.
    """
    if not settings.demo_password_reset_enabled:
        raise ValidationAppError("Şifre yenileme bu ortamda kapalı.")

    # Karşılaştırma sabit zamanlı: normal `==` ilk farklı karakterde döndüğü
    # için harcanan süre ölçülerek kod tahmin edilebilirdi.
    if not secrets.compare_digest(code, settings.demo_reset_code):
        raise AuthenticationError(_INVALID_RESET)

    user = db.execute(select(User).where(User.national_id == national_id)).scalar_one_or_none()
    if user is None:
        raise AuthenticationError(_INVALID_RESET)

    user.password_hash = hash_password(new_password)
    db.commit()
