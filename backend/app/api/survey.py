"""Yatırımcı risk profili anketinin uçları.

`/questions` ve `/score` KİMLİK DOĞRULAMASI İSTEMEZ ve bu bilinçli: ikisi de
veri yazmaz — sorular salt okunur, skorlama saf hesaptır. Kayıt akışında
kullanıcı henüz yokken de çağrılabilmeleri gerekiyor.

`/submit/{user_id}` YAZAR, dolayısıyla oturum ve sahiplik kontrolü ister:
anket puanı tüm uygunluk kontrolünün dayandığı beyandır, başkasının puanını
değiştirebilmek onu ele geçirmek olurdu (AK 5.4).
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, verify_user_access
from app.core.db import get_db
from app.core.exceptions import NotFoundError
from app.models import User
from app.schemas.survey import SurveyQuestions, SurveyResult, SurveyScoreRequest
from app.services import survey_service
from app.services.user_service import set_user_risk_survey

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/survey", tags=["survey"])


@router.get("/questions", response_model=SurveyQuestions)
def read_survey_questions() -> SurveyQuestions:
    """Anket içeriği: sorular, seçenekler, ürün matrisi, profil tanımları.

    Sorular arayüze GÖMÜLMEZ, buradan gelir. Aksi hâlde `test-config.json`
    değiştiğinde arayüz eski soruyu sormaya devam eder ve skor, sorulmayan
    bir soruya göre hesaplanırdı.
    """
    cfg = survey_service.config()
    return SurveyQuestions(
        meta=cfg["meta"],
        sorular=cfg["sorular"],
        urun_matrisi=cfg["urun_matrisi"],
        profiller=cfg["profiller"],
        arac_sirasi=cfg.get("arac_sirasi", []),
        araclar=cfg.get("araclar", {}),
    )


@router.post("/score", response_model=SurveyResult)
async def score_survey(payload: SurveyScoreRequest) -> SurveyResult:
    """Cevapları skorlar ve sonucu açıklayan metni üretir. HİÇBİR ŞEY YAZMAZ.

    Kayıt ekranı sonucu kullanıcıya göstermek için bunu çağırır; kaydetme
    `/api/auth/register` ile ayrı bir adımda olur. Böylece kullanıcı profilini
    görüp hesabı açmaktan vazgeçebilir ve arkada yarım bir kayıt kalmaz.

    400 → eksik/geçersiz cevap. Eksik cevabı 0 puan saymıyoruz: yarım
    bırakılmış bir anket "Korumacı" profil üretir ve kullanıcı bunu geçerli
    sanırdı (AK 5.5).
    """
    try:
        sonuc = survey_service.skorla(payload.answers)
    except survey_service.SurveyAnswerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    yorum = await survey_service.yorum_uret(sonuc)
    return SurveyResult(**sonuc, yorum=yorum)


@router.post("/submit/{user_id}", response_model=SurveyResult)
async def submit_survey(
    user_id: UUID,
    payload: SurveyScoreRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
) -> SurveyResult:
    """Anketi skorlar VE sonucu kullanıcıya kaydeder.

    Giriş yapmış ama anketi henüz doldurmamış kullanıcı için. Skorlama yine
    sunucuda: gönderilen tek şey ham cevaplardır, puan değil.

    Durdurucu kural tetiklendiğinde HİÇBİR ŞEY KAYDEDİLMEZ ama sonuç yine de
    döner — arayüz kullanıcıya hangi çelişkiyi düzeltmesi gerektiğini
    gösterebilsin diye. `sonuc_uretildi: false` geldiğinde puan yazılmamıştır.

    `risk_profile` puandan türetilerek birlikte güncellenir
    (`user_service.set_user_risk_survey`); ikisi tek işlemde yazılır.
    """
    verify_user_access(user_id, current_user)

    try:
        sonuc = survey_service.skorla(payload.answers)
    except survey_service.SurveyAnswerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if sonuc["sonuc_uretildi"] and sonuc["profil_seviyesi"] is not None:
        try:
            set_user_risk_survey(db, user_id, sonuc["profil_seviyesi"])
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=exc.message) from exc

    yorum = await survey_service.yorum_uret(sonuc)
    return SurveyResult(**sonuc, yorum=yorum)
