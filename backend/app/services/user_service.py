"""Kullanıcı risk profilini okuma/yazma.

Bu, projedeki İLK yazma yolu olan servistir (defter dışında): şimdiye kadar
tüm uçlar salt okurdu. Yazma kapısı bilinçli olarak dar tutuldu — yalnızca
`risk_profile` alanı güncellenir; e-posta, ad ya da portföy buradan
değiştirilemez.

NEDEN AJANA AÇILMIYOR. Bu fonksiyonlar için MCP tool'u YAZILMADI ve
yazılmamalı. `agents/scope.yaml` alım/satım/değiştirme fiillerini
`UNAUTHORIZED_ACTION` olarak sınıflandırıyor; sohbet üzerinden bir modelin
kullanıcının risk profilini değiştirebilmesi, prompt enjeksiyonuyla
("artık agresif profildesin") kullanıcının beyan ettiği risk toleransının
ele geçirilmesi demek olurdu. Profil yalnızca anket ekranından, kullanıcının
kendi eylemiyle değişir.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import RiskProfile
from app.core.exceptions import NotFoundError
from app.models import User
from app.schemas.user import UserRiskProfile


def _get_user(db: Session, user_id: UUID) -> User:
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise NotFoundError("Kullanıcı bulunamadı.")
    return user


def _to_schema(user: User) -> UserRiskProfile:
    # Seçenek listesi enum'dan üretiliyor, elle yazılmıyor: kademe sayısı
    # değişirse (4 -> 7) burası kendiliğinden güncellenir.
    return UserRiskProfile(
        user_id=user.id,
        risk_profile=user.risk_profile,
        available_profiles=list(RiskProfile),
    )


def get_user_risk_profile(db: Session, user_id: UUID) -> UserRiskProfile:
    """Kullanıcının kayıtlı risk profilini döner."""
    return _to_schema(_get_user(db, user_id))


def set_user_risk_profile(db: Session, user_id: UUID, risk_profile: RiskProfile) -> UserRiskProfile:
    """Anket sonucunu kaydeder ve profilin son hâlini döner.

    Aynı değerle çağrılmak hata değildir (idempotent): anket ekranı aynı
    sonucu tekrar gönderebilir, kullanıcıya hata göstermenin bir anlamı yok.
    """
    user = _get_user(db, user_id)
    user.risk_profile = risk_profile
    db.commit()
    db.refresh(user)
    return _to_schema(user)
