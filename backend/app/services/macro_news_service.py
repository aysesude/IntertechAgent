"""Canlı makro haber OKUMA servisi.

Yazan taraf `app/services/macro_news_ingest.py`'dir (batch/cron); bu ayrım
`price_service.py` / `price_ingest.py` ile aynı kalıp — okuma ve yazma
sorumlulukları ayrı, MCP tool'u yalnızca buradan okur, hiçbir dış sağlayıcıya
(yfinance) istek atmaz."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import MacroNewsSnapshot


def get_macro_news(
    db: Session,
    symbols: list[str],
    max_age_days: int | None = None,
    per_symbol: int | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Verilen sembollerin (bkz. app/providers/universe.py:macro_news_key)
    güncel canlı haberlerini döner: `{sembol: [{"headline","source","url",
    "published_at"}, ...]}`.

    Yalnızca `max_age_days` içinde YAYIMLANMIŞ satırlar döner — DB'de daha
    eski bir satır olsa bile (silinmemiş olabilir, retention penceresi daha
    geniş tutulur) sonuca girmez; "canlı" iddiasının karşılığı budur.

    Sembol başına en yeniden en eskiye sıralanır ve `per_symbol` ile
    kırpılır. Hiçbir sembol için haber yoksa boş sözlük döner — bu bir hata
    değildir, çağıran taraf (MCP tool) bunu NOT_FOUND'a çevirmeyi
    seçebilir."""
    if not symbols:
        return {}

    age_limit = max_age_days if max_age_days is not None else settings.macro_news_max_age_days
    limit = per_symbol if per_symbol is not None else settings.macro_news_per_symbol
    cutoff = datetime.now(timezone.utc) - timedelta(days=age_limit)

    rows = (
        db.execute(
            select(MacroNewsSnapshot)
            .where(MacroNewsSnapshot.symbol.in_(symbols))
            .where(MacroNewsSnapshot.published_at >= cutoff)
            .order_by(MacroNewsSnapshot.symbol, MacroNewsSnapshot.published_at.desc())
        )
        .scalars()
        .all()
    )

    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        bucket = grouped.setdefault(row.symbol, [])
        if len(bucket) >= limit:
            continue
        bucket.append(
            {
                "headline": row.headline,
                "source": row.source,
                "url": row.url,
                "published_at": row.published_at.isoformat(),
            }
        )
    return grouped
