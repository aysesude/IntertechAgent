"""Kullanıcı risk profilini okuma/yazma.

Bu, projedeki İLK yazma yolu olan servistir (defter dışında): şimdiye kadar
tüm uçlar salt okurdu. Yazma kapısı bilinçli olarak dar tutuldu — yalnızca
`risk_profile` alanı güncellenir; e-posta, ad ya da portföy buradan
değiştirilemez.

NEDEN YAZMA FONKSİYONLARI AJANA AÇILMIYOR. `set_user_risk_profile` ve
`set_user_risk_survey` için MCP tool'u YAZILMADI ve yazılmamalı.
`agents/scope.yaml` alım/satım/değiştirme fiillerini `UNAUTHORIZED_ACTION`
olarak sınıflandırıyor; sohbet üzerinden bir modelin kullanıcının risk
profilini değiştirebilmesi, prompt enjeksiyonuyla ("artık agresif
profildesin") kullanıcının beyan ettiği risk toleransının ele geçirilmesi
demek olurdu. Profil yalnızca anket ekranından, kullanıcının kendi
eylemiyle değişir.

2026-08-28 eki: OKUMA fonksiyonu `get_user_risk_survey` bu kapsamın DIŞINDA
— `mcp_server/tools/risk_tools.py`'de `get_user_risk_survey` adıyla MCP'ye
açıldı (bkz. `agents/portfolio_agent.py`, uygunluk/profil-uyumu bilgisini
sohbette göstermek için). Yukarıdaki risk yalnızca YAZMA için geçerli;
kullanıcının KENDİ puanını okuması bir "ele geçirme" değildir, zaten
`get_risk_assessment` de aynı alanı taşıyor (bkz. o tool'un dönüşü).
`get_and_consume_risk_survey_event` ise YAN ETKİLİ (tüketim yazıyor) olduğu
için ayrı, kendi tool'unda kalmaya devam ediyor (bkz. o fonksiyonun
docstring'i) — bu yeni tool tamamen salt okunur, hiçbir alanı değiştirmez.
"""

from datetime import datetime, timezone
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
from app.schemas.user import RiskSurveyEvent, UserRiskProfile, UserRiskSurvey
from app.services.advice_eligibility import mismatched_asset_classes, validate_survey_score
from app.services.portfolio_service import get_held_asset_classes


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
    # Sinyal 5 (profil_sapmasi, Yol A) bu anı okur — bkz.
    # get_and_consume_risk_survey_event. `set_user_risk_profile` (elle profil
    # değiştirme) buna KASITLI OLARAK dokunmaz: o bir anket olayı değildir.
    user.risk_survey_updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return _to_survey_schema(user)


def get_and_consume_risk_survey_event(db: Session, user_id: UUID) -> RiskSurveyEvent:
    """Bekleyen bir anket-yeniden-doldurma OLAYINI okur VE varsa aynı anda
    tüketilmiş sayar (atomik "oku ve tüket") — Sinyal 5'in (profil_sapmasi,
    Yol A) TEK girdisi.

    NEDEN ATOMİK. Tüketim işareti (`risk_survey_event_consumed_at`) bu
    fonksiyonun İÇİNDE, deterministik Python tarafında yazılır — LLM'in karar
    verdiği bir şey DEĞİLDİR. `agents/base.py`'nin "ajanlar veriye asla
    doğrudan erişmez" ve `agents/scope.yaml`'ın "ajan kullanıcının risk
    verisini asla değiştiremez" kurallarıyla çelişmez: burada değişen şey
    kullanıcının risk verisi değil, yalnızca "bu olay bir değerlendirmeye
    gösterildi" bayrağıdır — anketin kendisi ya da ondan türeyen profil hiç
    dokunulmadan kalır.

    `olay_var=False` dönüyorsa çağıran taraf diğer alanları OKUMAMALI
    (varsayılan değerleriyle gelirler, anlamsızdır).
    """
    user = _get_user(db, user_id)

    olay_var = user.risk_survey_score is not None and user.risk_survey_updated_at is not None
    if olay_var:
        consumed = user.risk_survey_event_consumed_at
        olay_var = consumed is None or consumed < user.risk_survey_updated_at

    if not olay_var:
        return RiskSurveyEvent(
            olay_var=False, yeni_profil=None, izin_verilmeyen_ve_elde_olan_siniflar=[]
        )

    elde_tutulan = get_held_asset_classes(db, user_id)
    # 2026-08-28 eki: bu fark artık `advice_eligibility.mismatched_asset_
    # classes`'ta merkezileşti (bkz. o fonksiyonun docstring'i) — aynı hesap
    # `agents/portfolio_agent.py`'de de kullanılıyor, tekrar yazılmıyor.
    izin_verilmeyen_ve_elde_olan = sorted(
        mismatched_asset_classes(elde_tutulan, user.risk_survey_score), key=lambda ac: ac.value
    )

    user.risk_survey_event_consumed_at = datetime.now(timezone.utc)
    db.commit()

    return RiskSurveyEvent(
        olay_var=True,
        yeni_profil=user.risk_profile,
        izin_verilmeyen_ve_elde_olan_siniflar=izin_verilmeyen_ve_elde_olan,
    )
