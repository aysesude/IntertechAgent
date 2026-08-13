import random
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from faker import Faker
import pandas as pd
from sqlalchemy import Column, Float, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import yfinance as yf

# Render PostgreSQL URL
RENDER_EXTERNAL_URL = "postgresql://finans_db_57rk_user:EPkJ3IXyvgHIqUHTmpL11u5ppPZenAvW@dpg-d9td763m8hqs73crb70g-a.frankfurt-postgres.render.com/finans_db_57rk"

engine = create_engine(RENDER_EXTERNAL_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    user_id = Column(String, primary_key=True)
    full_name = Column(String)
    risk_profile = Column(String)
    cash_try = Column(Float)

class Portfolio(Base):
    __tablename__ = "portfolio"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String)
    asset_type = Column(String)
    symbol = Column(String)
    quantity = Column(Float)
    avg_cost_try = Column(Float)

class PriceHistory(Base):
    __tablename__ = "price_history"
    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    price_date = Column(Date)
    close_price = Column(Float)

Base.metadata.create_all(bind=engine)

# CANLI DÖVİZ / ALTIN BAZ FİYATLARINI ALAN YARDIMCI FONKSİYON
def get_live_base_rates():
    rates = {"USDTRY": 47.20, "GRAM_ALTIN": 6050.00}
    try:
        tcmb_xml_url = "https://www.tcmb.gov.tr/kurlar/today.xml"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(tcmb_xml_url, headers=headers, timeout=5)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            for currency in root.findall("Currency"):
                if currency.attrib.get("CurrencyCode") == "USD":
                    usd_val = currency.find("BanknoteSelling").text or currency.find("ForexSelling").text
                    rates["USDTRY"] = float(usd_val)
                    break
        gold_ticker = yf.Ticker("GC=F")
        gold_data = gold_ticker.history(period="1d")
        if not gold_data.empty:
            ons_usd = float(gold_data["Close"].iloc[-1])
            rates["GRAM_ALTIN"] = (ons_usd / 31.1034768) * rates["USDTRY"]
    except Exception:
        pass
    return rates

def generate_multi_asset_user():
    session = SessionLocal()

    session.query(Portfolio).delete()
    session.query(User).delete()
    session.commit()

    user_id = "USR-MULTI-01"
    full_name = fake.name()
    risk_profile = random.choice(["Muhafazakar", "Dengeli", "Agresif"])
    cash_try = round(random.uniform(25000, 150000), 2)

    new_user = User(
        user_id=user_id,
        full_name=full_name,
        risk_profile=risk_profile,
        cash_try=cash_try
    )
    session.add(new_user)

    # Canlı Referans Kurlar
    live_rates = get_live_base_rates()

    # 1. HİSSE SENETLERİ HAVUZU
    stock_pool = [
        ("THYAO.IS", "Stock", 260.0, 300.0, 50, 200),
        ("GARAN.IS", "Stock", 80.0, 105.0, 100, 500),
        ("ASELS.IS", "Stock", 48.0, 62.0, 100, 400),
        ("EREGL.IS", "Stock", 35.0, 48.0, 150, 600),
        ("KCHOL.IS", "Stock", 190.0, 230.0, 50, 250)
    ]

    # 2. TEFAS FON KODLARI
    fund_codes = ["TI2", "TCD", "AFT", "PPF", "GTA"]
    selected_fund_codes = random.sample(fund_codes, k=random.randint(1, 2))
    selected_stocks = random.sample(stock_pool, k=2)

    # --- HİSSE SENETLERİ EKLENİYOR ---
    for symbol, asset_type, min_c, max_c, min_q, max_q in selected_stocks:
        qty = random.randint(min_q, max_q)
        cost = round(random.uniform(min_c, max_c), 2)
        session.add(Portfolio(user_id=user_id, asset_type=asset_type, symbol=symbol, quantity=qty, avg_cost_try=cost))

    # --- DÖVİZ VE ALTIN EKLENİYOR (DİNAMİK MALİYET) ---
    usd_cost = round(live_rates["USDTRY"] * random.uniform(0.85, 0.98), 2)
    session.add(Portfolio(user_id=user_id, asset_type="Currency", symbol="USDTRY", quantity=round(random.uniform(1000, 5000), 2), avg_cost_try=usd_cost))

    gold_cost = round(live_rates["GRAM_ALTIN"] * random.uniform(0.85, 0.98), 2)
    session.add(Portfolio(user_id=user_id, asset_type="Commodity", symbol="GRAM_ALTIN", quantity=round(random.uniform(15, 90), 2), avg_cost_try=gold_cost))

    # --- TEFAS FONLARI EKLENİYOR ---
    for code in selected_fund_codes:
        base_price = 3.0 if code != "PPF" else 115.0
        cost = round(base_price * random.uniform(0.85, 1.10), 4)
        qty = round(random.uniform(1000, 8000), 2) if code != "PPF" else round(random.uniform(100, 500), 2)
        session.add(Portfolio(user_id=user_id, asset_type="Fund", symbol=code, quantity=qty, avg_cost_try=cost))

    session.commit()
    session.close()
    print(f"👤 Kullanıcı Oluşturuldu: {full_name} ({user_id})")
    print(f"💾 Atanan Maliyetler (USD Maliyet: {usd_cost} TL, Altın Maliyet: {gold_cost} TL)")
    print("💾 Hisse, Döviz, Altın ve TEFAS Fon varlıkları Render PostgreSQL'e yazıldı.\n")
    return user_id

# Betiği Çalıştır
# ==============================================================================
# HÜCRE 2: CANLI PİYASA VERİSİ VE ÇOKLU VARLIK PORTFÖY DEĞERLEMESİ (İŞ BANKASI FON SERVİSİ)
# ==============================================================================

import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf

# --- 1. TCMB KURLAR SERVİSİ (XML TABANLI / %100 KESİNTİSİZ) ---
def get_evds_live_rates():
    rates = {"USDTRY": 47.20, "EURTRY": 51.50, "GRAM_ALTIN": 6050.00}
    tcmb_xml_url = "https://www.tcmb.gov.tr/kurlar/today.xml"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        response = requests.get(tcmb_xml_url, headers=headers, timeout=8)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            for currency in root.findall("Currency"):
                code = currency.attrib.get("CurrencyCode")
                if code == "USD":
                    usd_val = currency.find("BanknoteSelling").text or currency.find("ForexSelling").text
                    rates["USDTRY"] = round(float(usd_val), 4)
                elif code == "EUR":
                    eur_val = currency.find("BanknoteSelling").text or currency.find("ForexSelling").text
                    rates["EURTRY"] = round(float(eur_val), 4)
            print(f"✅ TCMB Resmi Kurları Çekildi: Dolar={rates['USDTRY']} TL, Euro={rates['EURTRY']} TL")
    except Exception as e:
        print(f"⚠️ TCMB XML çekim uyarısı: {e}")

    try:
        gold_ticker = yf.Ticker("GC=F")
        gold_data = gold_ticker.history(period="1d")
        if not gold_data.empty:
            ons_usd = float(gold_data["Close"].iloc[-1])
            gram_altin = (ons_usd / 31.1034768) * rates["USDTRY"]
            rates["GRAM_ALTIN"] = round(gram_altin, 2)
            print(f"✅ Canlı Gram Altın Çekildi: {rates['GRAM_ALTIN']} TL (Ons: ${ons_usd:,.2f})")
    except Exception as e:
        print(f"⚠️ Altın fiyatı yfinance uyarısı: {e}")

    return rates

# --- 2. İŞ BANKASI KAMUSAL FON SERVİSİ (HİBRİT / VERİTABANI YEDEK DOKUNUŞLU) ---
def get_fund_prices_isbank(fund_codes: list):
    session = SessionLocal()
    fund_prices = {}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    for code in fund_codes:
        fetched = False
        # A) İş Portföy / İş Bankası Kamusal Fon API'si Denemesi
        try:
            url = f"https://www.isportfoy.com.tr/api/v1/Fund/GetFundDetailHeader?fundCode={code}"
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if "Price" in data and data["Price"]:
                    price = float(data["Price"])
                    fund_prices[code] = round(price, 4)
                    print(f"✅ İş Portföy Servisi {code} Canlı Fiyatı: {price} TL")
                    fetched = True
        except Exception:
            pass

        # B) Eğer İş Bankası servisinden veri dönmezse, Veritabanımızdaki (price_history) En Son Fiyata Düş
        if not fetched:
            latest_record = session.query(PriceHistory)
                .filter(PriceHistory.symbol == code)
                .order_by(PriceHistory.price_date.desc())
                .first()

            if latest_record:
                fund_prices[code] = round(float(latest_record.close_price), 4)
                print(f"ℹ️ {code} için Veritabanı Son Fiyatı Kullanıldı: {fund_prices[code]} TL ({latest_record.price_date})")
            else:
                defaults = {"TI2": 2.1450, "TCD": 5.4200, "AFT": 0.3250, "PPF": 118.5000, "GTA": 2.5800}
                fund_prices[code] = defaults.get(code, 3.0)

    session.close()
    return fund_prices

# --- 3. BİST CANLI HİSSE FİYAT SERVİSİ ---
def get_live_stock_price(symbol: str) -> float:
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="1d")
        if not data.empty:
            return round(float(data["Close"].iloc[-1]), 2)
    except Exception:
        pass
    return 0.0

# --- 4. ANA PORTFÖY DEĞERLEME MOTORU ---
def run_full_multi_asset_demo(user_id: str):
    session = SessionLocal()

    print("🔄 Canlı Veriler Çekiliyor (yfinance + TCMB XML + İş Bankası Fon Servisi)...\n")

    evds_rates = get_evds_live_rates()
    user = session.query(User).filter(User.user_id == user_id).first()
    portfolio_items = pd.read_sql(f"SELECT * FROM portfolio WHERE user_id = '{user_id}'", con=engine)

    fund_symbols = portfolio_items[portfolio_items["asset_type"] == "Fund"]["symbol"].tolist()
    tefas_prices = get_fund_prices_isbank(fund_symbols) if fund_symbols else {}

    results = []
    total_cost = 0
    total_current_value = 0

    for _, row in portfolio_items.iterrows():
        symbol = row["symbol"]
        asset_type = row["asset_type"]
        qty = row["quantity"]
        cost = row["avg_cost_try"]

        if asset_type == "Stock":
            live_price = get_live_stock_price(symbol)
        elif asset_type == "Fund":
            live_price = tefas_prices.get(symbol, cost)
        elif symbol in evds_rates:
            live_price = evds_rates[symbol]
        else:
            live_price = cost

        if live_price == 0.0:
            live_price = cost

        item_cost = qty * cost
        item_value = qty * live_price
        pnl_try = item_value - item_cost
        pnl_pct = ((live_price - cost) / cost) * 100 if cost > 0 else 0

        total_cost += item_cost
        total_current_value += item_value

        type_labels = {
            "Stock": "Hisse Senedi",
            "Currency": "Döviz",
            "Commodity": "Emtia / Altın",
            "Fund": "TEFAS Yatırım Fonu"
        }

        results.append({
            "Varlık Türü": type_labels.get(asset_type, asset_type),
            "Sembol": symbol.replace(".IS", ""),
            "Adet / Miktar": f"{qty:,.2f}" if asset_type != "Stock" else f"{int(qty)}",
            "Ort. Maliyet (TL)": f"{cost:,.4f}" if asset_type == "Fund" else f"{cost:,.2f}",
            "Canlı Fiyat (TL)": f"{live_price:,.4f}" if asset_type == "Fund" else f"{live_price:,.2f}",
            "Toplam Maliyet (TL)": f"{item_cost:,.2f}",
            "Güncel Değer (TL)": f"{item_value:,.2f}",
            "Kâr / Zarar (TL)": f"{pnl_try:+,.2f}",
            "Getiri (%)": f"%{pnl_pct:+.2f}"
        })

    session.close()

    net_pnl = total_current_value - total_cost
    total_pnl_pct = (net_pnl / total_cost) * 100 if total_cost > 0 else 0

    user_summary_df = pd.DataFrame([{
        "Kullanıcı ID": user.user_id,
        "Ad Soyad": user.full_name,
        "Risk Profili": user.risk_profile,
        "Nakit Bakiye (TL)": f"{user.cash_try:,.2f} TL"
    }])

    print("\n========================================================================")
    print("📌 KULLANICI PROFİL BİLGİLERİ (Render PostgreSQL)")
    print("========================================================================")
    display(user_summary_df)

    portfolio_df = pd.DataFrame(results)

    print("\n========================================================================")
    print("🌐 ÇOĞUL VARLIKLI PORTFÖY DEĞERLEMESİ (BİST + TCMB + TEFAS)")
    print("========================================================================")
    display(portfolio_df)

    print("\n" + "—"*50)
    print(f"💰 TOPLAM YATIRILAN MALİYET : {total_cost:,.2f} TL")
    print(f"📊 TOPLAM CANLI PORTFÖY DEĞERİ: {total_current_value:,.2f} TL")
    print(f"🚀 PORTFÖY NET KÂR / ZARAR   : {net_pnl:+,.2f} TL (%{total_pnl_pct:+.2f})")
    print("—"*50)

# Kodu Çalıştır
run_full_multi_asset_demo("USR-MULTI-01")
demo_user_id = generate_multi_asset_user()
