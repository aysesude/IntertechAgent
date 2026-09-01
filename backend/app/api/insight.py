"""Hızlı Özet ucu — `agents/summary_agent.py`'yi çağırır.

SOHBETTEN AYRI. Panel bir düğmeyle açılıyor, sohbet mesajı değil: bu uç
`chat_service`'e hiçbir şey yazmaz, dolayısıyla panelin üretimi kullanıcının
sohbet geçmişini kirletmez (tasarım kararı, 1 Eylül 2026).
"""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from agents.summary_agent import KART_BASLIKLARI, KART_SIRASI, SummaryAgent
from app.api.deps import get_current_user, verify_user_access
from app.core.config import settings
from app.models import User
from app.schemas.insight import InsightCard, InsightCards

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/insight", tags=["insight"])

# Panelin tamamı için üst sınır. Beş tool paralel + bir LLM turu; ağ ya da
# sağlayıcı tökezlerse panel süresiz "yükleniyor"da kalmamalı. Süre dolarsa
# kartlar deterministik gövdeyle DEĞİL, dürüst bir "üretilemedi" metniyle
# döner — yarım veriyle özet yazmak uydurmaya açık kapıdır.
_ZAMAN_ASIMI_SANIYE = 30

_URETILEMEDI = "Özet şu anda üretilemedi, lütfen tekrar deneyin."


@router.get("/{user_id}", response_model=InsightCards)
async def read_insight(
    user_id: UUID,
    current_user: User | None = Depends(get_current_user),
) -> InsightCards:
    """Hızlı Özet panelinin dört kartı.

    Kartlar HER ÇAĞRIDA yeniden üretilir; sunucu tarafında önbellek yok
    (ürün kararı: paneli açmak yenilemek demek). İstemci tarafında da
    önbellek tutulmuyor.

    Hiçbir koşulda boş liste dönmez: tool'lar ya da LLM düşse bile dört kart
    döner, gövdeleri `degraded` işaretiyle gelir.
    """
    verify_user_access(user_id, current_user)

    agent = SummaryAgent(mcp_server_url=settings.mcp_server_url)
    try:
        kartlar = await asyncio.wait_for(
            agent.kartlari_uret(str(user_id)), timeout=_ZAMAN_ASIMI_SANIYE
        )
    except asyncio.TimeoutError:
        logger.warning("[INSIGHT] özet zaman aşımına uğradı: %s", user_id)
        kartlar = _bos_kartlar()
    except Exception:
        # Ajan içindeki her yol kendi hatasını yutuyor; buraya düşen bir
        # istisna beklenmeyen bir durumdur. Panel yine de açılmalı.
        logger.exception("[INSIGHT] özet üretilemedi: %s", user_id)
        kartlar = _bos_kartlar()

    if not kartlar:
        raise HTTPException(status_code=500, detail="Özet üretilemedi.")

    return InsightCards(
        user_id=str(user_id),
        generated_at=datetime.now(timezone.utc),
        cards=[InsightCard(**k) for k in kartlar],
    )


def _bos_kartlar() -> list[dict]:
    """Dört kart, dürüst bir "üretilemedi" gövdesiyle. Boş panel göstermek
    kullanıcıya "özet yok" der; oysa doğru bilgi "şu an üretilemedi"dir."""
    return [
        {"id": kart_id, "title": KART_BASLIKLARI[kart_id], "body": _URETILEMEDI, "degraded": True}
        for kart_id in KART_SIRASI
    ]
