from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, market, portfolio
from app.core.config import settings
from app.core.logging import setup_logging

setup_logging()

app = FastAPI(title="Akıllı Kişisel Finans Danışmanı API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portfolio.router)
app.include_router(portfolio.price_router)
app.include_router(market.router)
app.include_router(chat.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
