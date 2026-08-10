from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import NotFoundError
from app.schemas.portfolio import PortfolioSummary
from app.services.portfolio_service import get_portfolio_summary

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/{user_id}", response_model=PortfolioSummary)
def read_portfolio_summary(user_id: UUID, db: Session = Depends(get_db)) -> PortfolioSummary:
    try:
        return get_portfolio_summary(db, user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
