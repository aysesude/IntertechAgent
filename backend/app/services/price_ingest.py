"""Fiyat toplama servisi — price_history'ye yazan TEK taraf.

Çekirdek kural (upsert önceliği): bir (asset, gün) çakışmasında yalnızca daha
yüksek öncelikli kaynak mevcut satırı ezebilir:

    synthetic(0) < derived(1) < yfinance(2) < tefas/isportfoy(3) < tcmb(4)

Yani gerçek veri sentetiği ezer; sentetik gerçeği ASLA ezemez. `make seed`'in
birikmiş gerçek veriyi silmesi disiplinle değil bu kuralla imkânsızdır.

Her sembol denemesi `data_ingest_log`'a yazılır (AK 5.2/5.3): başarı da
başarısızlık da görünürdür; dashboard "veri X gündür güncellenemedi" uyarısını
buradan üretebilir.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import Text, case, cast, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import PRICE_SOURCE_PRIORITY, IngestStatus, PriceSource
from app.models import Asset, DataIngestLog, PriceHistory
from app.providers.base import PricePoint, ProviderError
from app.providers.derived import derive_points
from app.providers.registry import latest_chain, series_chain
from app.providers.universe import ASSET_UNIVERSE, SPEC_BY_SYMBOL, AssetSpec

logger = logging.getLogger(__name__)

_PRICE_QUANT = Decimal("0.000001")


@dataclass(frozen=True)
class IngestResult:
    symbol: str
    provider: PriceSource
    status: IngestStatus
    rows_upserted: int
    error_message: str | None = None


def _priority_case(column):
    """source kolonunu sayısal önceliğe çeviren SQL CASE ifadesi.

    Kolon metne cast edilir: PG'de enum kolonu, parametre olarak bağlanan
    varchar literallerle doğrudan karşılaştırılamaz (operator does not exist);
    SQLite'ta cast zararsızdır."""
    return case(
        {source.value: priority for source, priority in PRICE_SOURCE_PRIORITY.items()},
        value=cast(column, Text),
        else_=0,
    )


def upsert_prices(db: Session, asset_id, points: list[PricePoint]) -> int:
    """Kaynak öncelikli toplu upsert. Yazılan (eklenen + güncellenen) satır
    sayısını döndürür; öncelik kuralına takılan satırlar sayılmaz."""
    if not points:
        return 0

    fetched_at = datetime.now(timezone.utc)
    rows = [
        {
            "asset_id": asset_id,
            "price_date": p.price_date,
            "close_price": p.close_price.quantize(_PRICE_QUANT, rounding=ROUND_HALF_UP),
            "source": p.source.value,
            "fetched_at": fetched_at,
        }
        for p in points
    ]

    insert_fn = sqlite_insert if db.get_bind().dialect.name == "sqlite" else pg_insert
    statement = insert_fn(PriceHistory).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["asset_id", "price_date"],
        set_={
            "close_price": statement.excluded.close_price,
            "source": statement.excluded.source,
            "fetched_at": statement.excluded.fetched_at,
        },
        where=(
            _priority_case(statement.excluded.source)
            > _priority_case(PriceHistory.__table__.c.source)
        ),
        # rowcount PG'de bu deyim için güvenilir değil (-1 dönebiliyor); RETURNING
        # yalnızca gerçekten yazılan (öncelik kuralına takılmayan) satırları döndürür.
    ).returning(PriceHistory.__table__.c.id)
    written = len(db.execute(statement).fetchall())
    db.flush()
    return written


def _log(db: Session, result: IngestResult, asset_id) -> None:
    db.add(
        DataIngestLog(
            run_at=datetime.now(timezone.utc),
            provider=result.provider,
            symbol=result.symbol,
            asset_id=asset_id,
            status=result.status,
            rows_upserted=result.rows_upserted,
            error_message=result.error_message,
        )
    )


def _asset_id_by_symbol(db: Session, symbol: str):
    return db.execute(select(Asset.id).where(Asset.symbol == symbol)).scalar_one_or_none()


def _try_chain(db: Session, spec: AssetSpec, chain, fetch) -> IngestResult:
    """Zincirdeki sağlayıcıları sırayla dener; ilk başarılı sonucu upsert eder.

    Tümü başarısızsa FAILED loglanır ve DB'deki son bilinen fiyatlar yerinde
    kalır (zarif düşüş: silme yok, uydurma yok)."""
    asset_id = _asset_id_by_symbol(db, spec.symbol)
    if asset_id is None:
        result = IngestResult(
            spec.symbol,
            spec.data_source,
            IngestStatus.SKIPPED,
            0,
            "varlık DB'de yok — önce seed_assets çalıştırılmalı",
        )
        _log(db, result, None)
        return result

    errors: list[str] = []
    for provider, provider_symbol in chain:
        provider_name = type(provider).__name__
        try:
            points = fetch(provider, provider_symbol)
        except ProviderError as exc:
            errors.append(str(exc))
            logger.warning("Sağlayıcı düşüşü: %s", exc)
            continue
        if not points:
            errors.append(f"[{provider_name}] {provider_symbol}: veri yok")
            continue
        rows = upsert_prices(db, asset_id, points)
        result = IngestResult(spec.symbol, points[0].source, IngestStatus.SUCCESS, rows)
        _log(db, result, asset_id)
        return result

    result = IngestResult(
        spec.symbol,
        spec.data_source,
        IngestStatus.FAILED,
        0,
        " | ".join(errors) or "denenecek sağlayıcı yok",
    )
    _log(db, result, asset_id)
    return result


def _ingest_derived(db: Session, spec: AssetSpec, start: date, end: date) -> IngestResult:
    """Türetilmiş varlık: kaynağının GERÇEK (sentetik olmayan) satırlarından
    hesaplanır. Sentetik satırdan türetim yapılmaz — derived(1) > synthetic(0)
    olduğundan sahte bir öncelik yükselmesi yaratırdı."""
    asset_id = _asset_id_by_symbol(db, spec.symbol)
    base_id = _asset_id_by_symbol(db, spec.derived_from)
    if asset_id is None or base_id is None:
        result = IngestResult(
            spec.symbol, PriceSource.DERIVED, IngestStatus.SKIPPED, 0, "varlık/kaynak DB'de yok"
        )
        _log(db, result, asset_id)
        return result

    rows = db.execute(
        select(PriceHistory.price_date, PriceHistory.close_price)
        .where(
            PriceHistory.asset_id == base_id,
            PriceHistory.price_date >= start,
            PriceHistory.price_date <= end,
            PriceHistory.source != PriceSource.SYNTHETIC,
        )
        .order_by(PriceHistory.price_date)
    ).all()
    if not rows:
        result = IngestResult(
            spec.symbol,
            PriceSource.DERIVED,
            IngestStatus.SKIPPED,
            0,
            f"kaynak {spec.derived_from} için gerçek veri yok",
        )
        _log(db, result, asset_id)
        return result

    base_points = [
        PricePoint(price_date=d, close_price=p, source=PriceSource.DERIVED) for d, p in rows
    ]
    upserted = upsert_prices(db, asset_id, derive_points(base_points, spec.derived_factor))
    result = IngestResult(spec.symbol, PriceSource.DERIVED, IngestStatus.SUCCESS, upserted)
    _log(db, result, asset_id)
    return result


def _ordered_specs(symbols: list[str] | None) -> list[AssetSpec]:
    specs = (
        ASSET_UNIVERSE
        if symbols is None
        else [SPEC_BY_SYMBOL[s] for s in symbols if s in SPEC_BY_SYMBOL]
    )
    # Türetilmişler en sona: kaynakları önce yazılmış olmalı.
    return sorted(specs, key=lambda s: s.data_source == PriceSource.DERIVED)


def run_backfill(
    db: Session, days: int = 365, symbols: list[str] | None = None
) -> list[IngestResult]:
    """Tarihsel gerçek seriyi çekip yazar (bir kerelik / aralıklı çalıştırılır)."""
    end = date.today()
    start = end - timedelta(days=days - 1)
    results: list[IngestResult] = []
    for spec in _ordered_specs(symbols):
        if spec.data_source == PriceSource.SYNTHETIC:
            continue  # sentetik varlıkların canlı kaynağı yok; seed üretir
        if spec.data_source == PriceSource.DERIVED:
            results.append(_ingest_derived(db, spec, start, end))
            continue
        results.append(
            _try_chain(
                db,
                spec,
                series_chain(spec),
                lambda provider, sym: provider.fetch_series(sym, start, end),
            )
        )
    db.commit()
    return results


def run_daily_update(db: Session, symbols: list[str] | None = None) -> list[IngestResult]:
    """Günün fiyatlarını çeker (cron/job). Her gün çalışırsa price_history'de
    gerçek seri kendiliğinden birikir."""
    today = date.today()
    results: list[IngestResult] = []
    for spec in _ordered_specs(symbols):
        if spec.data_source == PriceSource.SYNTHETIC:
            continue
        if spec.data_source == PriceSource.DERIVED:
            results.append(_ingest_derived(db, spec, today - timedelta(days=7), today))
            continue
        results.append(
            _try_chain(
                db,
                spec,
                latest_chain(spec),
                lambda provider, sym: ([point] if (point := provider.fetch_latest(sym)) else []),
            )
        )
    db.commit()
    return results
