"""Deterministik sentetik veri üreticisi.

50 kullanıcı, her birine 5-15 varlık (hisse/altın/döviz/tahvil), bu varlıklara ait
12 aylık işlem geçmişi (alım, bazen satım) ve tüm varlık evreni için 12 aylık günlük
fiyat serisi (random walk) üretir. Sabit `SEED` sayesinde çalıştırma parametreleri
(miktarlar, fiyat hareketleri, kullanıcı seçimleri) her çalıştırmada aynıdır; tarihler
betiğin çalıştırıldığı güne (`date.today()`) göre ankraj edilir.

Çalıştırmadan önce `alembic upgrade head` ile migration'ların uygulanmış olması gerekir.

Kullanım:
    python -m data.generate_dummy
"""

import random
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from faker import Faker
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from app.core.config import AssetClass, settings
from app.models import (
    Asset,
    ChatSession,
    Holding,
    Message,
    PriceHistory,
    Portfolio,
    Transaction,
    TransactionType,
    User,
)

SEED = 42
NUM_USERS = 50
MIN_HOLDINGS_PER_USER = 5
MAX_HOLDINGS_PER_USER = 15
HISTORY_DAYS = 365

# Sadece bu üretici içindir: gerçek piyasa verisi değil, sentetik random walk
# parametreleridir (varlık sınıfı başına günlük ortalama getiri, günlük volatilite).
ASSET_CLASS_DAILY_DRIFT_VOLATILITY: dict[AssetClass, tuple[float, float]] = {
    AssetClass.STOCK: (0.0004, 0.020),
    AssetClass.GOLD: (0.0002, 0.008),
    AssetClass.CURRENCY: (0.0001, 0.006),
    AssetClass.BOND: (0.00015, 0.003),
}

QUANTITY_PRECISION: dict[AssetClass, Decimal] = {
    AssetClass.STOCK: Decimal("1"),
    AssetClass.GOLD: Decimal("0.01"),
    AssetClass.CURRENCY: Decimal("1"),
    AssetClass.BOND: Decimal("1"),
}

ASSET_UNIVERSE: list[dict[str, object]] = [
    # --- STOCK (BIST) ---
    {"symbol": "THYAO", "name": "Türk Hava Yolları", "asset_class": AssetClass.STOCK, "currency": "TRY", "base_price": "285.00"},
    {"symbol": "ASELS", "name": "Aselsan", "asset_class": AssetClass.STOCK, "currency": "TRY", "base_price": "62.50"},
    {"symbol": "GARAN", "name": "Garanti BBVA", "asset_class": AssetClass.STOCK, "currency": "TRY", "base_price": "98.30"},
    {"symbol": "AKBNK", "name": "Akbank", "asset_class": AssetClass.STOCK, "currency": "TRY", "base_price": "58.20"},
    {"symbol": "BIMAS", "name": "BİM Mağazalar", "asset_class": AssetClass.STOCK, "currency": "TRY", "base_price": "540.00"},
    {"symbol": "EREGL", "name": "Ereğli Demir Çelik", "asset_class": AssetClass.STOCK, "currency": "TRY", "base_price": "45.10"},
    {"symbol": "KCHOL", "name": "Koç Holding", "asset_class": AssetClass.STOCK, "currency": "TRY", "base_price": "175.00"},
    {"symbol": "SASA", "name": "Sasa Polyester", "asset_class": AssetClass.STOCK, "currency": "TRY", "base_price": "12.80"},
    {"symbol": "TUPRS", "name": "Tüpraş", "asset_class": AssetClass.STOCK, "currency": "TRY", "base_price": "165.00"},
    {"symbol": "PGSUS", "name": "Pegasus Hava Taşımacılığı", "asset_class": AssetClass.STOCK, "currency": "TRY", "base_price": "425.00"},
    {"symbol": "SISE", "name": "Şişecam", "asset_class": AssetClass.STOCK, "currency": "TRY", "base_price": "38.90"},
    {"symbol": "FROTO", "name": "Ford Otosan", "asset_class": AssetClass.STOCK, "currency": "TRY", "base_price": "890.00"},
    {"symbol": "TCELL", "name": "Turkcell", "asset_class": AssetClass.STOCK, "currency": "TRY", "base_price": "82.40"},
    {"symbol": "YKBNK", "name": "Yapı Kredi Bankası", "asset_class": AssetClass.STOCK, "currency": "TRY", "base_price": "27.60"},
    {"symbol": "VESTL", "name": "Vestel", "asset_class": AssetClass.STOCK, "currency": "TRY", "base_price": "44.30"},
    # --- GOLD ---
    {"symbol": "XAUTRY", "name": "Gram Altın", "asset_class": AssetClass.GOLD, "currency": "TRY", "base_price": "2450.00"},
    {"symbol": "CEYREK", "name": "Çeyrek Altın", "asset_class": AssetClass.GOLD, "currency": "TRY", "base_price": "4020.00"},
    {"symbol": "YARIM", "name": "Yarım Altın", "asset_class": AssetClass.GOLD, "currency": "TRY", "base_price": "8040.00"},
    {"symbol": "TAMALTIN", "name": "Tam Altın", "asset_class": AssetClass.GOLD, "currency": "TRY", "base_price": "16080.00"},
    {"symbol": "CUMHUR", "name": "Cumhuriyet Altını", "asset_class": AssetClass.GOLD, "currency": "TRY", "base_price": "16500.00"},
    # --- CURRENCY ---
    {"symbol": "USDTRY", "name": "Amerikan Doları", "asset_class": AssetClass.CURRENCY, "currency": "TRY", "base_price": "34.20"},
    {"symbol": "EURTRY", "name": "Euro", "asset_class": AssetClass.CURRENCY, "currency": "TRY", "base_price": "37.10"},
    {"symbol": "GBPTRY", "name": "İngiliz Sterlini", "asset_class": AssetClass.CURRENCY, "currency": "TRY", "base_price": "43.50"},
    {"symbol": "CHFTRY", "name": "İsviçre Frangı", "asset_class": AssetClass.CURRENCY, "currency": "TRY", "base_price": "38.90"},
    # --- BOND ---
    {"symbol": "TRT101", "name": "Devlet Tahvili 10Y", "asset_class": AssetClass.BOND, "currency": "TRY", "base_price": "980.00"},
    {"symbol": "TRT052", "name": "Devlet Tahvili 5Y", "asset_class": AssetClass.BOND, "currency": "TRY", "base_price": "990.00"},
    {"symbol": "EUROBOND1", "name": "Hazine Eurobond", "asset_class": AssetClass.BOND, "currency": "USD", "base_price": "97.50"},
    {"symbol": "OST2027", "name": "Özel Sektör Tahvili 2027", "asset_class": AssetClass.BOND, "currency": "TRY", "base_price": "950.00"},
]


def generate_price_series(base_price: Decimal, asset_class: AssetClass, days: int) -> list[Decimal]:
    """Verilen varlık sınıfının drift/volatilite parametreleriyle günlük random walk üretir."""
    drift, volatility = ASSET_CLASS_DAILY_DRIFT_VOLATILITY[asset_class]
    prices = [base_price]
    price = base_price
    for _ in range(days - 1):
        daily_return = round(random.gauss(drift, volatility), 6)
        price = price * (Decimal("1") + Decimal(str(daily_return)))
        price = max(price, Decimal("0.01"))
        price = price.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        prices.append(price)
    return prices


def random_lot_quantity(asset_class: AssetClass) -> Decimal:
    if asset_class == AssetClass.STOCK:
        return Decimal(random.randint(5, 150))
    if asset_class == AssetClass.GOLD:
        return Decimal(str(round(random.uniform(0.5, 15), 2)))
    if asset_class == AssetClass.CURRENCY:
        return Decimal(random.randint(50, 3000))
    if asset_class == AssetClass.BOND:
        return Decimal(random.randint(5, 80))
    raise ValueError(f"Bilinmeyen asset_class: {asset_class}")


def quantize_quantity(value: Decimal, asset_class: AssetClass) -> Decimal:
    return value.quantize(QUANTITY_PRECISION[asset_class], rounding=ROUND_HALF_UP)


def build_holding_and_transactions(
    portfolio_id, asset_id, asset_class: AssetClass, price_by_date: dict[date, Decimal], end_date: date
) -> tuple[Holding, list[Transaction]]:
    """Bir varlık için rastgele alım (ve bazen satım) işlemleri üretir, bunlardan
    nihai Holding.quantity ve ağırlıklı ortalama maliyeti hesaplar."""
    num_buys = random.randint(1, 4)
    buy_days_ago = random.sample(range(30, HISTORY_DAYS), num_buys)

    transactions: list[Transaction] = []
    total_bought = Decimal("0")
    total_cost = Decimal("0")
    for days_ago in buy_days_ago:
        qty = random_lot_quantity(asset_class)
        tx_date = end_date - timedelta(days=days_ago)
        price = price_by_date[tx_date]
        transactions.append(
            Transaction(
                portfolio_id=portfolio_id,
                asset_id=asset_id,
                transaction_type=TransactionType.BUY,
                quantity=qty,
                price=price,
                transaction_date=datetime.combine(tx_date, datetime.min.time()),
            )
        )
        total_bought += qty
        total_cost += qty * price

    total_sold = Decimal("0")
    if random.random() < 0.3:
        sell_days_ago = random.randint(1, 29)
        sell_fraction = round(random.uniform(0.1, 0.4), 4)
        sell_qty = quantize_quantity(total_bought * Decimal(str(sell_fraction)), asset_class)
        if sell_qty > 0:
            tx_date = end_date - timedelta(days=sell_days_ago)
            price = price_by_date[tx_date]
            transactions.append(
                Transaction(
                    portfolio_id=portfolio_id,
                    asset_id=asset_id,
                    transaction_type=TransactionType.SELL,
                    quantity=sell_qty,
                    price=price,
                    transaction_date=datetime.combine(tx_date, datetime.min.time()),
                )
            )
            total_sold = sell_qty

    final_quantity = total_bought - total_sold
    avg_cost_price = (total_cost / total_bought).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    holding = Holding(
        portfolio_id=portfolio_id,
        asset_id=asset_id,
        quantity=final_quantity,
        avg_cost_price=avg_cost_price,
    )
    return holding, transactions


def wipe_existing_data(session: Session) -> None:
    """Tabloları FK sırasına saygılı şekilde temizler; betik tekrar çalıştırılabilir olsun diye."""
    for model in (Message, ChatSession, Transaction, Holding, PriceHistory, Portfolio, Asset, User):
        session.execute(delete(model))
    session.commit()


def main() -> None:
    random.seed(SEED)
    Faker.seed(SEED)
    fake = Faker("tr_TR")
    # fake.unique'in "gorulen deger" onbellegi process boyunca kalici; betik
    # ayni process icinde birden fazla kez cagrilirsa (ornegin testlerde)
    # onceki calismadan kalan degerler yuzunden ekstra rastgele cekim yapip
    # determinizmi bozar. Her main() cagrisinda temizleniyor.
    fake.unique.clear()

    end_date = date.today()
    start_date = end_date - timedelta(days=HISTORY_DAYS - 1)

    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        wipe_existing_data(session)

        # --- Varlık evreni ---
        assets: list[Asset] = []
        price_by_date_per_asset: dict[str, dict[date, Decimal]] = {}
        for spec in ASSET_UNIVERSE:
            asset = Asset(
                symbol=spec["symbol"],
                name=spec["name"],
                asset_class=spec["asset_class"],
                currency=spec["currency"],
            )
            assets.append(asset)
        session.add_all(assets)
        session.flush()  # id'leri almak için

        price_rows: list[PriceHistory] = []
        for asset, spec in zip(assets, ASSET_UNIVERSE):
            series = generate_price_series(Decimal(spec["base_price"]), spec["asset_class"], HISTORY_DAYS)
            by_date = {start_date + timedelta(days=i): price for i, price in enumerate(series)}
            price_by_date_per_asset[asset.symbol] = by_date
            price_rows.extend(
                PriceHistory(asset_id=asset.id, price_date=d, close_price=p) for d, p in by_date.items()
            )
        session.add_all(price_rows)
        session.commit()

        # --- Kullanıcılar, portföyler, holding + transaction ---
        for _ in range(NUM_USERS):
            user = User(email=fake.unique.email(), full_name=fake.name())
            session.add(user)
            session.flush()

            portfolio = Portfolio(user_id=user.id)
            session.add(portfolio)
            session.flush()

            num_holdings = random.randint(MIN_HOLDINGS_PER_USER, MAX_HOLDINGS_PER_USER)
            chosen = random.sample(list(zip(assets, ASSET_UNIVERSE)), num_holdings)

            for asset, spec in chosen:
                holding, transactions = build_holding_and_transactions(
                    portfolio_id=portfolio.id,
                    asset_id=asset.id,
                    asset_class=spec["asset_class"],
                    price_by_date=price_by_date_per_asset[asset.symbol],
                    end_date=end_date,
                )
                session.add(holding)
                session.add_all(transactions)

        session.commit()

        print(f"{NUM_USERS} kullanıcı, {len(assets)} varlık, {len(price_rows)} fiyat kaydı üretildi.")
        print(f"Fiyat serisi aralığı: {start_date} -> {end_date}")


if __name__ == "__main__":
    main()
