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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="*", default=None, help="yalnızca bu semboller")
    args = parser.parse_args()

    engine = create_engine(settings.database_url)
    with Session(engine) as session:
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
