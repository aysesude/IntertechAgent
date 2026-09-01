"""Sentetik veri orkestratörü: varlıklar -> sentetik fiyatlar -> işlem defteri.

Üç adım, üç modül:
    data/seed_assets.py             varlık evreni (providers/universe.py'den)
    data/seed_prices_synthetic.py   faktör modelli sentetik fiyat serileri
    data/seed_ledger.py             kullanıcı + portföy + İŞLEM DEFTERİ
                                    (holdings defterden türetilir)

Temizlik kapsamı:
- Varsayılan: kullanıcı tabloları + YALNIZCA sentetik fiyat satırları.
  Biriken GERÇEK fiyatlar (backfill/daily_update) korunur — sentetik,
  gerçeği yapısal olarak ezemez (bkz. services/price_ingest.py).
- --wipe-all: her şey (fiyat geçmişi, varlıklar, ingest logu dahil) silinir.
  Yalnızca bozuk bir DB'yi sıfırlamak için.

Tarihler ANKRAJ gününe göre kurulur; ankraj varsayılan olarak gerçek fiyat
verisinin bittiği gündür (bkz. data/anchor.py). `ANCHOR_DATE` ortam değişkeni
verilirse o kullanılır.

Kullanım:
    python -m data.generate_dummy [--wipe-all]

Önce `alembic upgrade head` gerekir.
"""

import argparse

from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Asset,
    ChatSession,
    DataIngestLog,
    Holding,
    Message,
    Portfolio,
    PriceHistory,
    Transaction,
    User,
)
from data.anchor import resolve_anchor_date
from data.seed_assets import seed_assets
from data.seed_ledger import (
    MAX_HOLDINGS_PER_USER,
    MIN_HOLDINGS_PER_USER,
    NUM_USERS,
    TOPLAM_KULLANICI,
    seed_ledger,
)
from data.seed_prices_synthetic import HISTORY_DAYS, seed_prices_synthetic

__all__ = [
    "MAX_HOLDINGS_PER_USER",
    "MIN_HOLDINGS_PER_USER",
    "NUM_USERS",
    "TOPLAM_KULLANICI",
    "HISTORY_DAYS",
    "main",
]


def wipe_user_data(session: Session) -> None:
    """Kullanıcı tarafını temizler (FK sırasına saygılı). Fiyat geçmişine ve
    varlıklara DOKUNMAZ."""
    for model in (Message, ChatSession, Transaction, Holding, Portfolio, User):
        session.execute(delete(model))
    session.commit()


def wipe_everything(session: Session) -> None:
    """Tam sıfırlama: birikmiş gerçek fiyat verisi DAHİL her şey gider.
    Bilinçli bir karar gerektirir (--wipe-all)."""
    for model in (
        Message,
        ChatSession,
        Transaction,
        Holding,
        DataIngestLog,
        PriceHistory,
        Portfolio,
        Asset,
        User,
    ):
        session.execute(delete(model))
    session.commit()


def main(wipe_all: bool = False) -> None:
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        if wipe_all:
            wipe_everything(session)
        else:
            wipe_user_data(session)

        assets_by_symbol = seed_assets(session)
        price_rows = seed_prices_synthetic(session, assets_by_symbol)
        session.commit()
        tx_count = seed_ledger(session)

        print(
            f"{TOPLAM_KULLANICI} kullanıcı ({NUM_USERS} üretilmiş + demo personası), "
            f"{len(assets_by_symbol)} varlık, "
            f"{price_rows} sentetik fiyat satırı, {tx_count} işlem üretildi."
        )
        ankraj = resolve_anchor_date(session)
        kaynak = "ANCHOR_DATE" if settings.anchor_date is not None else "gerçek fiyat verisi"
        print(f"Ankraj: {ankraj} ({kaynak}; geçmiş {HISTORY_DAYS} gün, işlem günleri)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wipe-all",
        action="store_true",
        help="fiyat geçmişi ve varlıklar dahil HER ŞEYİ silip baştan üret",
    )
    args = parser.parse_args()
    main(wipe_all=args.wipe_all)
