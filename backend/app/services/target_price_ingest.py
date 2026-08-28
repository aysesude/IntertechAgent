"""Hedef fiyat (analist tavsiyesi) toplama servisi — target_prices'a yazan
TEK taraf (CLAUDE.md "yazma kapıları" ilkesi, price_ingest.upsert_prices ile
aynı sınıf).

**Neden RAG değil, neden bu tablo:** hedef fiyat hızlı bayatlayan bir rakam
— aynı sebeple `haber`/`analiz`/`makro` doküman türleri 2026-08-22'de RAG'dan
kaldırıldı (bkz. data/documents/README.md). Anlamsal arama güncelliği
bilmez; sekiz ay önceki bir hedefi bugünün cevabı olarak getirip kendinden
emin bir tonla sunardı. Sayı burada, ilişkisel DB'de yaşar; agent tarafı
(agents/price_query.py::hedef_fiyat_niyeti, market_agent.py::
_hedef_fiyat_yaniti) bunu LLM'e YENİDEN YAZDIRMADAN, ham/tarihli bir blok
olarak sunar — tıpkı `_kap_blogu`/`_gundem_blogu`'nun canlı KAP/piyasa
başlıklarını sundu gibi.

**Neden tarihçe değil, TEK satır/kurum:** kaynak (Şeker Yatırım "Tavsiye
Listesi") kendisi bir anlık görüntü, birikimli bir arşiv değil. Doküman
kendi notunda "snapshot al ve dondur" diyor — her ingest çalıştığında eski
satır güncellenir (upsert), üstüne yenisi eklenmez. Bir revizyon olduğunda
(hedef fiyat değiştiğinde) eski değer `previous_target_price`/
`revision_direction` alanlarına taşınır; bu da doküman şemasının "hedef
yükseltildi mi düşürüldü mü" ihtiyacını, ayrı bir zaman serisi tutmadan
karşılar.

**Lisans notu:** yalnızca SAYISAL alanlar (kurum, tavsiye, hedef fiyat,
kapanış, tarih) alınır — kaynağın rapor/yorum METNİ hiç kopyalanmıyor
(bu kaynakta zaten yok). Kaynak URL'si ve rapor tarihi her satırla
birlikte saklanır (AK 5.1) ki sunum katmanı kurumu/tarihi göstersin.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import Asset, TargetPrice
from app.providers.base import ProviderError, TargetPricePoint
from app.providers.sekeryatirim_p import fetch_target_prices

logger = logging.getLogger(__name__)


def _revizyon_yonu(eski: Decimal, yeni: Decimal) -> str:
    if yeni > eski:
        return "yukseltme"
    if yeni < eski:
        return "dusurme"
    return "koruma"


def upsert_target_prices(db: Session, points: list[TargetPricePoint]) -> int:
    """Kurum başına TEK satır upsert eder. DB'de eşleşen sembol yoksa (varlık
    evreninde tanımlı değilse) o satır ATLANIR — hata değil, CLAUDE.md
    "zarif düşüş" ilkesi. Yazılan (eklenen + güncellenen) satır sayısını
    döndürür."""
    if not points:
        return 0

    semboller = {p.symbol for p in points}
    asset_id_by_symbol = dict(
        db.execute(select(Asset.symbol, Asset.id).where(Asset.symbol.in_(semboller))).all()
    )

    atlanan: list[str] = []
    mevcut_hedefler = dict(
        db.execute(
            select(TargetPrice.asset_id, TargetPrice.target_price).where(
                TargetPrice.asset_id.in_(asset_id_by_symbol.values())
            )
        ).all()
    )

    fetched_at = datetime.now(timezone.utc)
    rows = []
    for p in points:
        asset_id = asset_id_by_symbol.get(p.symbol)
        if asset_id is None:
            atlanan.append(p.symbol)
            continue
        eski_hedef = mevcut_hedefler.get(asset_id)
        rows.append(
            {
                "asset_id": asset_id,
                "institution": p.institution,
                "recommendation": p.recommendation,
                "target_price": p.target_price,
                "currency": p.currency,
                "price_at_report": p.price_at_report,
                "previous_target_price": eski_hedef,
                "revision_direction": (
                    _revizyon_yonu(eski_hedef, p.target_price) if eski_hedef is not None else None
                ),
                "report_date": p.report_date,
                "source_url": p.source_url,
                "fetched_at": fetched_at,
            }
        )

    if atlanan:
        logger.warning(
            "target_price_ingest: %d sembol varlık evreninde bulunamadı, atlandı: %s",
            len(atlanan),
            ", ".join(sorted(atlanan)),
        )
    if not rows:
        return 0

    insert_fn = sqlite_insert if db.get_bind().dialect.name == "sqlite" else pg_insert
    statement = insert_fn(TargetPrice).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["asset_id", "institution"],
        set_={
            "recommendation": statement.excluded.recommendation,
            "target_price": statement.excluded.target_price,
            "currency": statement.excluded.currency,
            "price_at_report": statement.excluded.price_at_report,
            "previous_target_price": statement.excluded.previous_target_price,
            "revision_direction": statement.excluded.revision_direction,
            "report_date": statement.excluded.report_date,
            "source_url": statement.excluded.source_url,
            "fetched_at": statement.excluded.fetched_at,
        },
    ).returning(TargetPrice.__table__.c.id)
    written = len(db.execute(statement).fetchall())
    db.commit()
    return written


def run_target_price_ingest(db: Session) -> int:
    """Şeker Yatırım'dan çekip upsert eder. Sağlayıcı tamamen erişilemezse
    (`ProviderError`) DB'deki son bilinen satırlar YERİNDE kalır — hiçbir şey
    silinmez, hata loglanır."""
    try:
        points = fetch_target_prices()
    except ProviderError as exc:
        logger.error("target_price_ingest: sağlayıcı başarısız: %s", exc)
        return 0
    return upsert_target_prices(db, points)
