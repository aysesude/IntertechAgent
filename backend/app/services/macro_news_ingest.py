"""Canlı makro haber toplama servisi — `macro_news_snapshot`'a yazan TEK taraf.

Neden bu tablo var / neden batch (istek anında değil): bkz.
app/models/macro_news_snapshot.py modül docstring'i.

`price_ingest.py` ile aynı zarif-düşüş ilkesi: her sembol bağımsız denenir,
biri başarısız olursa (sağlayıcı hatası, o sembolde hiç haber yok) yalnızca o
sembol atlanır — tüm çalıştırma düşmez, çünkü bu veri hiçbir sinyali
TETİKLEMEZ, yalnızca `investment_strategy` metnini besler (bkz.
agents/prompts/risk_signals.md).
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import AssetClass, settings
from app.models import MacroNewsSnapshot
from app.providers.base import NewsItem, ProviderError
from app.providers.universe import ASSET_UNIVERSE, macro_news_key, yfinance_news_ticker
from app.providers.yfinance_p import YFinanceProvider

logger = logging.getLogger(__name__)


def _news_targets() -> dict[str, tuple[AssetClass, str]]:
    """`macro_news_key -> (asset_class, yfinance_ticker)` eşlemesi, evrendeki
    TÜM varlıklardan türetilir. Aynı anahtara (ör. dört altın sikke türü de
    XAUTRY'ye) birden fazla `AssetSpec` düşebilir — burada tekilleştirilir,
    çekim anahtar başına yalnızca BİR kez yapılır."""
    targets: dict[str, tuple[AssetClass, str]] = {}
    for spec in ASSET_UNIVERSE:
        ticker = yfinance_news_ticker(spec)
        key = macro_news_key(spec)
        if ticker is None or key is None:
            continue
        targets.setdefault(key, (spec.asset_class, ticker))
    return targets


def upsert_news(
    db: Session, symbol: str, asset_class: AssetClass, items: list[NewsItem], fetched_at: datetime
) -> int:
    """`items`'i `macro_news_snapshot`a yazar. `(symbol, url)` çiftinde
    çakışan satırlar ATLANIR (do-nothing) — aynı haber birden fazla
    çalıştırmada tekrar gelirse kopya birikmez, ama ilk görüldüğü
    `fetched_at`/`created_at` korunur (bu da doğrudur: haberin bizim
    tarafımızdan ne zaman İLK görüldüğü değişmemeli)."""
    if not items:
        return 0

    rows = [
        {
            "symbol": symbol,
            "asset_class": asset_class.value,
            "headline": item.headline,
            "source": item.source,
            "url": item.url,
            "published_at": item.published_at,
            "fetched_at": fetched_at,
        }
        for item in items
    ]

    insert_fn = sqlite_insert if db.get_bind().dialect.name == "sqlite" else pg_insert
    statement = insert_fn(MacroNewsSnapshot).values(rows)
    statement = statement.on_conflict_do_nothing(index_elements=["symbol", "url"])
    # rowcount PG'de bu deyim için güvenilir değil (-1 dönebiliyor — psycopg,
    # ON CONFLICT DO NOTHING'in çakışmadan atladığı satırları rowcount'a doğru
    # yansıtmıyor); price_ingest.py'deki upsert_prices ile aynı çözüm: RETURNING
    # yalnızca gerçekten yazılan (çakışmayan) satırları döndürür.
    statement = statement.returning(MacroNewsSnapshot.__table__.c.id)
    written = len(db.execute(statement).fetchall())
    db.flush()
    return written


def run_macro_news_update(
    db: Session, provider: YFinanceProvider | None = None
) -> list[dict[str, object]]:
    """Her canlı-haberi-olabilecek sembol için (Döviz + Kıymetli Maden,
    bkz. `_news_targets`) son haberleri çeker ve upsert eder. Ardından
    `settings.macro_news_retention_days`'ten eski satırları siler.

    `date.today()`/`datetime.now()` burada BİLİNÇLİ olarak kullanılır
    (`data/daily_update.py` ile aynı ilke): bu sentetik/deterministik bir
    üretim değil, GERÇEK dış dünyadan gelen canlı veri."""
    provider = provider or YFinanceProvider()
    fetched_at = datetime.now(timezone.utc)
    results: list[dict[str, object]] = []

    for symbol, (asset_class, ticker) in sorted(_news_targets().items()):
        try:
            items = provider.fetch_news(ticker, limit=settings.macro_news_per_symbol)
        except ProviderError as exc:
            logger.warning("Makro haber çekimi başarısız: %s", exc)
            results.append({"symbol": symbol, "status": "failed", "error": str(exc)})
            continue

        written = upsert_news(db, symbol, asset_class, items, fetched_at)
        results.append(
            {"symbol": symbol, "status": "success", "found": len(items), "written": written}
        )

    cutoff = fetched_at - timedelta(days=settings.macro_news_retention_days)
    db.execute(delete(MacroNewsSnapshot).where(MacroNewsSnapshot.fetched_at < cutoff))
    db.commit()
    return results
