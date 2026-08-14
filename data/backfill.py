"""Gerçek tarihsel fiyat serilerini çekip price_history'ye yazar.

Bir kerelik (veya aralıklı) çalıştırılır; günlük akış için data.daily_update.
Sentetik satırları ezmesi güvenlidir (kaynak önceliği); tersi imkânsızdır.

Kullanım:
    python -m data.backfill [--days 365] [--symbols THYAO USDTRY ...]
"""

import argparse

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import IngestStatus, settings
from app.services.price_ingest import run_backfill


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=365, help="kaç günlük geçmiş (varsayılan 365)")
    parser.add_argument("--symbols", nargs="*", default=None, help="yalnızca bu semboller")
    args = parser.parse_args()

    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        results = run_backfill(session, days=args.days, symbols=args.symbols)

    for r in results:
        marker = {"success": "+", "skipped": "-", "failed": "!", "partial": "~"}[r.status.value]
        line = f"  {marker} {r.symbol:<10} {r.provider.value:<10} {r.rows_upserted:>5} satır"
        if r.error_message:
            line += f"  ({r.error_message})"
        print(line)

    failed = sum(1 for r in results if r.status == IngestStatus.FAILED)
    ok = sum(1 for r in results if r.status == IngestStatus.SUCCESS)
    total_rows = sum(r.rows_upserted for r in results)
    print(f"\n{ok} sembol başarılı, {failed} başarısız; toplam {total_rows} satır yazıldı.")
    if failed:
        print("Başarısız semboller data_ingest_log'da kayıtlı; DB'deki son veriler korunur.")


if __name__ == "__main__":
    main()
