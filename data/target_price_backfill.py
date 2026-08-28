"""Şeker Yatırım "Tavsiye Listesi"nden hedef fiyat/tavsiye çekip
target_prices'a yazar (upsert — bkz. app/services/target_price_ingest.py
docstring'i).

Bir kerelik / aralıklı çalıştırılır ("snapshot al ve dondur" — demo günü
yaklaşana kadar tekrar çalıştırmayın, tutarlılık güncellikten önemli).

Kullanım:
    python -m data.target_price_backfill
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.target_price_ingest import run_target_price_ingest
from data.seed_assets import seed_assets


def main() -> None:
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        # Varlık kataloğu ÖNCE hizalanır — bkz. data/backfill.py'deki aynı
        # gerekçe (fiyat yazmak için varlığın DB kaydı gerekiyor).
        seed_assets(session)
        written = run_target_price_ingest(session)

    print(f"{written} satır yazıldı (eklendi/güncellendi).")


if __name__ == "__main__":
    main()
