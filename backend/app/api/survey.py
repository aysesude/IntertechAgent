"""Yatırımcı risk profili anketinin uçları.

İkisi de KİMLİK DOĞRULAMASI İSTEMEZ ve bu bilinçli: anket kayıt akışının
içinde, kullanıcı henüz yokken doldurulur. Hiçbiri veri yazmaz — sorular
salt okunur, skorlama saf hesaptır. Anket sonucu ancak `/api/auth/register`
ile kullanıcıya bağlanır.
"""

import logging

from fastapi import APIRouter, HTTPException

from app.schemas.survey import SurveyQuestions, SurveyResult, SurveyScoreRequest
from app.services import survey_service

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
