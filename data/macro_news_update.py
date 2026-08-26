"""Döviz ve Kıymetli Maden için canlı piyasa haberini çekip
macro_news_snapshot'a yazar (cron/job için) — bkz. app/models/
macro_news_snapshot.py ve app/services/macro_news_ingest.py (neden bu
tablo var, neden istek anında değil batch).

`data/daily_update.py` ile aynı çalıştırma kalıbı; ayrı bir script olmasının
nedeni farklı veri türü (haber, fiyat değil) ve farklı kapsam (yalnızca
Döviz+Kıymetli Maden) olması — ikisini tek script'te birleştirmek "günün
fiyatlarını çek" ile "haber çek" gibi iki ayrı sorumluluğu karıştırırdı.

Kullanım:
    python -m data.macro_news_update
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.macro_news_ingest import run_macro_news_update


def main() -> None:
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        results = run_macro_news_update(session)

    for r in results:
        marker = "+" if r["status"] == "success" else "!"
        line = f"  {marker} {r['symbol']:<10}"
        if r["status"] == "success":
            line += f" {r['found']:>2} bulundu, {r['written']:>2} yeni yazıldı"
        else:
            line += f" {r['error']}"
        print(line)

    failed = sum(1 for r in results if r["status"] == "failed")
    print(f"\nBitti; {failed} sembol başarısız.")


if __name__ == "__main__":
    main()
