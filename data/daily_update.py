"""Günün fiyatlarını çekip price_history'ye yazar (cron/job için).

Her gün çalıştığında gerçek seri kendiliğinden birikir: bir ay sonra 30 günlük
gerçek geçmiş vardır ve risk hesapları giderek daha az sentetik veriye dayanır.

Kullanım:
    python -m data.daily_update [--symbols THYAO USDTRY ...]
"""

import argparse

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import IngestStatus, settings
from app.services.price_ingest import run_daily_update
from data.seed_assets import seed_assets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="*", default=None, help="yalnızca bu semboller")
    args = parser.parse_args()

    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        # Varlık kataloğu ÖNCE hizalanır.
        #
        # Fiyat yazmak için varlığın DB kaydı gerekiyor; yoksa sembol
        # sessizce atlanıyordu ("varlık DB'de yok"). Sunucuda tam bu oldu:
        # evrene yeni bir fon eklendi, backfill onu atladı ve belgelenen sıra
        # ("önce backfill, sonra seed") yeni varlıklarda çalışmaz hâle geldi —
        # doğrusu seed → backfill → seed olurdu, yani prosedür varlığın yaşına
        # göre değişiyordu.
        #
        # `seed_assets` idempotent ve YALNIZCA katalog tablosuna dokunur:
        # fiyatlara, işlem defterine ve kullanıcı verisine değmez. Burada
        # çağrılınca sıra her durumda aynı kalıyor.
        seed_assets(session)
        results = run_daily_update(session, symbols=args.symbols)

    for r in results:
        marker = {"success": "+", "skipped": "-", "failed": "!", "partial": "~"}[r.status.value]
        line = f"  {marker} {r.symbol:<10} {r.provider.value:<10} {r.rows_upserted:>5} satır"
        if r.error_message:
            line += f"  ({r.error_message})"
        print(line)

    failed = sum(1 for r in results if r.status == IngestStatus.FAILED)
    print(f"\nBitti; {failed} sembol başarısız (detay data_ingest_log'da).")


if __name__ == "__main__":
    main()
