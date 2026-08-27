"""Risk değerlendirmesi ucu.

`portfolio.py` gibi bu uç da AJAN ÇAĞIRMAZ, servisi doğrudan okur: dashboard
açılışında sorulmuş bir soru yok, araya LLM koymak ekranı model hızına bağlar
ve halüsinasyon yüzeyi açar. Ajanlar yalnızca sohbet yolunda devrededir.

Buradaki sayısal değerlerin HİÇBİRİ dil modeli tarafından üretilmez;
`risk_service` hesaplar (CLAUDE.md §4 "uydurmama ilkesi").
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, verify_user_access
from app.core.config import RiskProfile
from app.core.db import get_db
from app.core.exceptions import NotFoundError
from app.models import User
from app.schemas.risk import RiskAssessment
from app.services.risk_service import get_risk_assessment

router = APIRouter(prefix="/api/risk", tags=["risk"])


@router.get("/{user_id}", response_model=RiskAssessment)
def read_risk_assessment(
    user_id: UUID,
    profile_override: RiskProfile | None = Query(
        None,
        description=(
            "Verilirse hesap bu profile göre yapılır; kullanıcının KAYITLI "
            "profili değişmez ('ya agresif olsaydım?' senaryosu)."
        ),
    ),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
) -> RiskAssessment:
    """7 kademeli risk seviyesi, yıllık volatilite, VaR, Sharpe ve teşhis.

    Yeterli fiyat geçmişi yoksa `risk_level` ve metrikler `null` döner,
    tahmini bir değerle DOLDURULMAZ (AK 2.7 / 5.5); sebep `warnings`
    listesinde yazar. Arayüz bu durumda "hesaplanamadı" göstermeli, 0 değil.

    `scenarios` ürün sahibi kararıyla kapalıdır (bkz. risk_service): risk
    yalnızca tespit/uyarı içindir, ne yapılacağını önermek kapsam dışı.
    """
    verify_user_access(user_id, current_user)
    try:
        return get_risk_assessment(db, user_id, profile_override)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
