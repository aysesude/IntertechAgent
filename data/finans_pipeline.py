# ==============================================================================
# 1 YILLIK GEÇMİŞ VERİ ÇEKİCİ PIPELINE (VS CODE / STANDART PYTHON VERSION)
# ==============================================================================

from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

import pandas as pd
import requests
from sqlalchemy import Column, Date, Float, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from tefas import Crawler as TefasCrawler
import yfinance as yf

# Render PostgreSQL Bağlantı Cümlesi
RENDER_EXTERNAL_URL = (
    "postgresql://finans_db_57rk_user:EPkJ3IXyvgHIqUHTmpL11u5ppPZenAvW@"
    "dpg-d9td763m8hqs73crb70g-a.frankfurt-postgres.render.com/finans_db_57rk"
)

engine = create_engine(RENDER_EXTERNAL_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    asset_name = Column(String)
    price_date = Column(Date, nullable=False)
    close_price = Column(Float, nullable=False)


# Tabloyu oluştur (Yoksa)
Base.metadata.create_all(bind=engine)

FUND_NAME_MAP = {
    "TI2": "İş Portföy BİST 100 Dışı Şirketler Hissesi Fonu",
    "TCD": "Tacirler Portföy Değişken Fon",
    "AFT": "Ak Portföy Yeni Teknolojiler Yabancı Hisse Fonu",
    "PPF": "Deniz Portföy Para Piyasası Fonu",
    "GTA": "Garanti Portföy Altın Fonu",
}

STOCK_NAME_MAP = {
    "THYAO.IS": "Türk Hava Yolları",
    "GARAN.IS": "Garanti BBVA",
    "ASELS.IS": "Aselsan",
    "EREGL.IS": "Ereğli Demir Çelik",
    "KCHOL.IS": "Koç Holding",
}


def fetch_tefas_history_1year(fund_codes: list, days=365):
    """
    TEFAS, 2026'da eski fundturkey.com.tr/api/DB/BindHistoryInfo endpoint'ini
    kaldırdı. Yeni backend fon bazlı çalışıyor (tefas.gov.tr/api/funds/...)
    ve 1/3/6/12/36/60 aylık sabit "periyod" değerleri kabul ediyor.

    Bu yüzden elle HTTP isteği atmak yerine, bu değişikliği takip eden
    `tefas-crawler` (pip install tefas-crawler) paketini kullanıyoruz.
    """
    session = SessionLocal()

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    print(
        f"\n⏳ TEFAS Fonları için 1 Yıllık ({start_date.strftime('%d.%m.%Y')} - "
        f"{end_date.strftime('%d.%m.%Y')}) Geçmiş Veri Çekiliyor..."
    )

    tefas = TefasCrawler()

    for code in fund_codes:
        try:
            fund_name = FUND_NAME_MAP.get(code, f"{code} Yatırım Fonu")

            df = tefas.fetch(
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                name=code,
                columns=["date", "code", "price"],
            )

            added_count = 0

            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    p_date = row["date"]
                    if hasattr(p_date, "date"):
                        p_date = p_date.date()
                    if row["price"] is None:
                        continue
                    c_price = round(float(row["price"]), 4)

                    existing = (
                        session.query(PriceHistory)
                        .filter(
                            PriceHistory.symbol == code,
                            PriceHistory.price_date == p_date,
                        )
                        .first()
                    )

                    if not existing:
                        ph = PriceHistory(
                            symbol=code,
                            asset_name=fund_name,
                            price_date=p_date,
                            close_price=c_price,
                        )
                        session.add(ph)
                        added_count += 1

                session.commit()
                print(
                    f"  ✅ {fund_name} ({code}) - Toplam {len(df)} gün çekildi "
                    f"({added_count} yeni satır eklendi)."
                )
            else:
                print(f"  ⚠️ {code} için veri dönmedi.")

        except Exception as e:
            session.rollback()
            print(f"  ❌ {code} fonu hatası: {e}")

    session.close()


def fetch_stocks_history_1year(stock_symbols: list):
    session = SessionLocal()
    print("\n⏳ BİST Hisseleri için 1 Yıllık Geçmiş Veri Çekiliyor...")

    for symbol in stock_symbols:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="1y")

            if not df.empty:
                clean_symbol = symbol.replace(".IS", "")
                asset_name = STOCK_NAME_MAP.get(symbol, clean_symbol)
                added_count = 0

                for index, row in df.iterrows():
                    p_date = index.date()
                    c_price = round(float(row["Close"]), 2)

                    existing = (
                        session.query(PriceHistory)
                        .filter(
                            PriceHistory.symbol == clean_symbol,
                            PriceHistory.price_date == p_date,
                        )
                        .first()
                    )

                    if not existing:
                        ph = PriceHistory(
                            symbol=clean_symbol,
                            asset_name=asset_name,
                            price_date=p_date,
                            close_price=c_price,
                        )
                        session.add(ph)
                        added_count += 1

                session.commit()
                print(
                    f"  ✅ {asset_name} ({clean_symbol}) - Toplam {len(df)} gün çekildi "
                    f"({added_count} yeni satır eklendi)."
                )
            else:
                print(f"  ⚠️ {symbol} için veri dönmedi.")

        except Exception as e:
            session.rollback()
            print(f"  ❌ {symbol} hisse hatası: {e}")

    session.close()


def fetch_macro_history_1year():
    session = SessionLocal()
    print("\n⏳ Döviz ve Altın için 1 Yıllık Geçmiş Veri Çekiliyor...")

    try:
        usd_df = yf.Ticker("USDTRY=X").history(period="1y")
        eur_df = yf.Ticker("EURTRY=X").history(period="1y")
        gold_df = yf.Ticker("GC=F").history(period="1y")

        # 1. Dolar Çekimi
        usd_count = 0
        for index, row in usd_df.iterrows():
            p_date = index.date()
            c_price = round(float(row["Close"]), 4)
            existing = (
                session.query(PriceHistory)
                .filter(
                    PriceHistory.symbol == "USDTRY",
                    PriceHistory.price_date == p_date,
                )
                .first()
            )
            if not existing:
                session.add(
                    PriceHistory(
                        symbol="USDTRY",
                        asset_name="Amerikan Doları",
                        price_date=p_date,
                        close_price=c_price,
                    )
                )
                usd_count += 1
        session.commit()
        print(f"  ✅ USDTRY - {usd_count} yeni satır eklendi.")

        # 2. Euro Çekimi
        eur_count = 0
        for index, row in eur_df.iterrows():
            p_date = index.date()
            c_price = round(float(row["Close"]), 4)
            existing = (
                session.query(PriceHistory)
                .filter(
                    PriceHistory.symbol == "EURTRY",
                    PriceHistory.price_date == p_date,
                )
                .first()
            )
            if not existing:
                session.add(
                    PriceHistory(
                        symbol="EURTRY",
                        asset_name="Euro",
                        price_date=p_date,
                        close_price=c_price,
                    )
                )
                eur_count += 1
        session.commit()
        print(f"  ✅ EURTRY - {eur_count} yeni satır eklendi.")

        # 3. Gram Altın Çekimi (Ons * USDTRY / 31.1035)
        gold_count = 0
        for index, row in gold_df.iterrows():
            p_date = index.date()
            ons_usd = float(row["Close"])

            usd_record = (
                session.query(PriceHistory)
                .filter(
                    PriceHistory.symbol == "USDTRY",
                    PriceHistory.price_date == p_date,
                )
                .first()
            )

            if usd_record:
                usd_rate = usd_record.close_price
                gram_altin = round((ons_usd / 31.1034768) * usd_rate, 2)

                existing = (
                    session.query(PriceHistory)
                    .filter(
                        PriceHistory.symbol == "GRAM_ALTIN",
                        PriceHistory.price_date == p_date,
                    )
                    .first()
                )

                if not existing:
                    session.add(
                        PriceHistory(
                            symbol="GRAM_ALTIN",
                            asset_name="Gram Altın (TL)",
                            price_date=p_date,
                            close_price=gram_altin,
                        )
                    )
                    gold_count += 1
        session.commit()
        print(f"  ✅ GRAM_ALTIN - {gold_count} yeni satır eklendi.")

    except Exception as e:
        session.rollback()
        print(f"  ❌ Döviz/Altın hatası: {e}")

    session.close()


def print_database_summary():
    summary_query = """
    SELECT 
        symbol AS "Sembol", 
        asset_name AS "Varlık Adı", 
        COUNT(*) AS "Toplam Gün Sayısı",
        MIN(price_date) AS "En Eski Tarih",
        MAX(price_date) AS "En Güncel Tarih"
    FROM price_history 
    GROUP BY symbol, asset_name 
    ORDER BY symbol;
    """
    df = pd.read_sql(summary_query, con=engine)

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 1000)

    print("\n" + "=" * 80)
    print("📊 RENDER POSTGRESQL - 1 YILLIK GEÇMİŞ VERİ TABLOSU ÖZETİ")
    print("=" * 80)
    print(df.to_string(index=False))
    print("=" * 80 + "\n")


if __name__ == "__main__":
    # 1. TEFAS Fonları
    sample_funds = ["TI2", "TCD", "AFT", "PPF", "GTA"]
    fetch_tefas_history_1year(sample_funds, days=365)

    # 2. BİST Hisseleri
    sample_stocks = ["THYAO.IS", "GARAN.IS", "ASELS.IS", "EREGL.IS", "KCHOL.IS"]
    fetch_stocks_history_1year(sample_stocks)

    # 3. Döviz ve Altın
    fetch_macro_history_1year()

    # 4. Veritabanı Özet Raporu
    print_database_summary()
