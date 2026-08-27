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

from app.core.config import (
    RiskProfile,
    risk_profile_for_survey_score,
    survey_score_band,
)
from app.core.exceptions import NotFoundError
from app.models import User
from app.schemas.user import UserRiskProfile, UserRiskSurvey
from app.services.advice_eligibility import validate_survey_score


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
    """Profili DOĞRUDAN yazar ve son hâlini döner.

    Aynı değerle çağrılmak hata değildir (idempotent): arayüz aynı sonucu
    tekrar gönderebilir, kullanıcıya hata göstermenin bir anlamı yok.

    KAYITLI ANKET PUANINI SİLER. Profil artık anket puanından türeyen bir
    alan; doğrudan yazılması "kullanıcı profilini elle değiştirdi" demektir
    ve elde duran puan o değişikliği açıklamaz. Puanı olduğu gibi bırakmak,
    birbirini tutmayan iki cevap saklamak olurdu: puan 6 (Agresif) derken
    profil Muhafazakâr görünürdü. `None` dürüst olan: "kayıtlı bir anket
    sonucu yok, profil elle belirlendi."

    Anket sonucunu kaydetmek için `set_user_risk_survey` kullanılmalı.
    """
    user = _get_user(db, user_id)
    user.risk_profile = risk_profile
    user.risk_survey_score = None
    db.commit()
    db.refresh(user)
    return _to_schema(user)


def _to_survey_schema(user: User) -> UserRiskSurvey:
    puan = user.risk_survey_score
    return UserRiskSurvey(
        user_id=user.id,
        risk_survey_score=puan,
        risk_profile=user.risk_profile,
        # Puan yoksa bant da yok: kayıtlı profilin bandını döndürmek,
        # kullanıcının vermediği bir cevabı vermiş gibi göstermek olurdu.
        score_band=survey_score_band(user.risk_profile) if puan is not None else None,
    )


def get_user_risk_survey(db: Session, user_id: UUID) -> UserRiskSurvey:
    """Kullanıcının anket puanını ve ondan türeyen profili döner.

    Puan `None` olabilir (anket hiç doldurulmamış); profil yine de dolu
    döner, çünkü `users.risk_profile` her satırda zorunludur.
    """
    return _to_survey_schema(_get_user(db, user_id))


def set_user_risk_survey(db: Session, user_id: UUID, survey_score: int) -> UserRiskSurvey:
    """Anket puanını kaydeder VE profili ondan türetir.

    İkisi tek işlemde yazılıyor: puan yetkili alan, profil türev. Ayrı
    yazılsalardı arada bir hata olduğunda kullanıcı puanı 6 ama profili
    Muhafazakâr olan bir satırla kalırdı ve risk motoru yanlış tabloyu
    kullanırdı.

    Doğrulama burada da yapılıyor (`validate_survey_score`), Pydantic'te
    olmasına rağmen: servis HTTP katmanına güvenmemeli — seed ve ileride
    yazılacak betikler bu fonksiyonu doğrudan çağırabilir.
    """
    validate_survey_score(survey_score)
    user = _get_user(db, user_id)
    user.risk_survey_score = survey_score
    user.risk_profile = risk_profile_for_survey_score(survey_score)
    db.commit()
    db.refresh(user)
    return _to_survey_schema(user)
