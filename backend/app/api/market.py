"""TODO: Piyasa Araştırma Ajanı (RAG) hazır olduğunda gerçek endpoint'ler eklenecek."""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/news")
def read_market_news() -> None:
    raise HTTPException(status_code=501, detail="TODO: Piyasa Araştırma Ajanı henüz uygulanmadı")
