"""Sentetik kullanıcılar + İŞLEM DEFTERİ üretir; holdings DEFTERDEN türetilir.

Eski üreticiden temel farklar:
- Her portföy önce DEPOSIT ile fonlanır; her alım/satımın nakit ayağı yazılır.
  Defter her an dengelidir (nakit = SUM(cash_amount_try) >= 0).
- İşlem tarihleri fiyatın gerçekten VAR OLDUĞU günlere hizalanır (işlem
  günleri); hafta sonuna denk alım artık mümkün değildir.
- Fiyatlar price_history'den OKUNUR (kaynağı ne olursa olsun); maliyet
  bugünkü fiyattan geriye türetilmez — zarardaki portföyler de doğal olarak
  oluşur.
- holdings elle YAZILMAZ; ledger_service.rebuild_holdings üretir. Böylece
  seed, mutabakat değişmezinin (I1) ilk kanıtı olur.

Deterministiktir (SEED=42): kullanıcılar, profiller, arketipler, işlem
günleri ve miktarlar her çalıştırmada aynıdır.
"""

import random
import uuid
from datetime import datetime, time, timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from faker import Faker
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import RISK_MAX_CATEGORY_WEIGHT, AssetClass, RiskProfile, settings
from app.models import Asset, PriceHistory, TransactionType
from app.services.ledger_service import position_as_of, rebuild_holdings, record_transaction

SEED = 42
NUM_USERS = 50
# Test/mutabakat sözleşmesi: kullanıcı başına işlem GÖRMÜŞ varlık sayısı aralığı.
MIN_HOLDINGS_PER_USER = 5
MAX_HOLDINGS_PER_USER = 15

# Hisse alım/satım komisyonu (brüt tutarın oranı); diğer sınıflarda 0.
STOCK_FEE_RATE = Decimal("0.0015")
# Vadeli mevduat aylık faizi (INTEREST kaydı olarak deftere işlenir).
TIME_DEPOSIT_MONTHLY_RATE = Decimal("0.03")

QUANTITY_PRECISION: dict[AssetClass, Decimal] = {
    AssetClass.STOCK: Decimal(1),
    AssetClass.PRECIOUS_METAL: Decimal("0.01"),
    AssetClass.CURRENCY: Decimal(1),
    AssetClass.BOND: Decimal(1),
    AssetClass.CASH: Decimal("0.01"),
}

# Portföy arketipleri: sınıf ağırlıkları + sınıf başına kaç varlık seçileceği.
# Tamamen rastgele seçim tüm portföyleri birbirine benzetiyordu; AK-2.6
# "farklı yapılar farklı sonuç üretebilmeli" der.
PORTFOLIO_ARCHETYPES: dict[str, dict[AssetClass, tuple[float, int]]] = {
    "mixed": {
        AssetClass.STOCK: (0.35, 3),
        AssetClass.PRECIOUS_METAL: (0.20, 2),
        AssetClass.CURRENCY: (0.20, 2),
        AssetClass.BOND: (0.15, 2),
        AssetClass.CASH: (0.10, 1),
    },
    "concentrated_equity": {
        AssetClass.STOCK: (0.75, 4),
        AssetClass.PRECIOUS_METAL: (0.05, 1),
        AssetClass.CURRENCY: (0.10, 1),
        AssetClass.CASH: (0.10, 1),
    },
    "diversified": {
        AssetClass.STOCK: (0.25, 4),
        AssetClass.PRECIOUS_METAL: (0.20, 2),
        AssetClass.CURRENCY: (0.20, 3),
        AssetClass.BOND: (0.25, 3),
        AssetClass.CASH: (0.10, 2),
    },
    "cash_heavy": {
        AssetClass.STOCK: (0.10, 1),
        AssetClass.PRECIOUS_METAL: (0.10, 1),
        AssetClass.CURRENCY: (0.15, 2),
        AssetClass.BOND: (0.20, 2),
        AssetClass.CASH: (0.45, 2),
    },
}
PORTFOLIO_ARCHETYPE_CYCLE = list(PORTFOLIO_ARCHETYPES)

_TRY_QUANT = Decimal("0.0001")


def _tx_datetime(d) -> datetime:
    return datetime.combine(d, time(hour=11), tzinfo=timezone.utc)


def _risk_profile_for_archetype(
    archetype: dict[AssetClass, tuple[float, int]],
) -> RiskProfile:
    """ÜRÜN SAHİBİ KARARI (2026-08, Not 5): risk profili artık üretilecek
    portföyün BAĞIMSIZ bir döngüsü değil, en riskli kategorinin (Hisse)
    hedef ağırlığından türetilir — "profil önce belirlenir, portföy ona göre
    kurulur" ilkesinin (Not 3) dummy veri karşılığı. Hisse ağırlığını
    RISK_MAX_CATEGORY_WEIGHT sınırı içinde barındırabilecek EN DÜŞÜK (en az
    riskli) profil seçilir; böylece üretilen her portföy kendi profilinin
    kategori sınırları içinde kalır, RISK_PROFILE_TARGET_ALLOCATION'ın eski
    bağımsız döngüsündeki gibi "Korumacı kullanıcıda %75 hisse" gibi
    tutarsızlıklar bir daha oluşmaz.

    Eşikler config.py'den okunduğu için, tablo değişirse burası da kendini
    günceller — elle eşleme yazılmadı."""
    stock_weight = Decimal(str(archetype.get(AssetClass.STOCK, (0.0, 0))[0]))
    for profile in (
        RiskProfile.CONSERVATIVE,
        RiskProfile.BALANCED,
        RiskProfile.GROWTH,
        RiskProfile.AGGRESSIVE,
    ):
        if stock_weight <= RISK_MAX_CATEGORY_WEIGHT[profile][AssetClass.STOCK]:
            return profile
    return (
        RiskProfile.AGGRESSIVE
    )  # sınırı en geniş profil bile aşarsa (olmamalı) yine de bir profil dön


def _load_price_book(
    session: Session,
) -> tuple[dict[str, Asset], dict[uuid.UUID, dict], dict[uuid.UUID, list]]:
    """price_history'yi belleğe alır: varlık başına {gün: fiyat} + sıralı günler."""
    assets = {
        a.symbol: a for a in session.execute(select(Asset).where(Asset.is_active)).scalars().all()
    }
    prices: dict[uuid.UUID, dict] = {a.id: {} for a in assets.values()}
    rows = session.execute(
        select(PriceHistory.asset_id, PriceHistory.price_date, PriceHistory.close_price)
    ).all()
    for asset_id, price_date, close_price in rows:
        if asset_id in prices:
            prices[asset_id][price_date] = close_price
    days = {asset_id: sorted(book) for asset_id, book in prices.items()}
    return assets, prices, days


def _fx_rate_on(prices, days, fx_asset_id, on_date) -> Decimal:
    """O günün kuru; o gün kur yoksa önceki en yakın işlem günü."""
    book = prices[fx_asset_id]
    if on_date in book:
        return book[on_date]
    earlier = [d for d in days[fx_asset_id] if d <= on_date]
    if not earlier:
        raise RuntimeError(f"{on_date} öncesinde kur verisi yok")
    return book[earlier[-1]]


def seed_ledger(session: Session) -> int:
    """Kullanıcı + portföy + defter üretir; üretilen işlem sayısını döndürür.

    Çağıran, kullanıcı tablolarını önceden temizlemiş olmalıdır
    (generate_dummy.wipe_user_data)."""
    from app.models import Portfolio, User  # döngüsel görünümü önlemek için yerel

    rng = random.Random(SEED)
    Faker.seed(SEED)
    fake = Faker("tr_TR")
    fake.unique.clear()

    assets, prices, days_by_asset = _load_price_book(session)
    usdtry_id = assets["USDTRY"].id

    assets_by_class: dict[AssetClass, list[Asset]] = {}
    for asset in assets.values():
        assets_by_class.setdefault(asset.asset_class, []).append(asset)
    for asset_list in assets_by_class.values():
        asset_list.sort(key=lambda a: a.symbol)  # determinizm sözlük sırasına bağlı kalmasın

    anchor = settings.anchor_date
    tx_count = 0

    for user_index in range(NUM_USERS):
        archetype = PORTFOLIO_ARCHETYPES[
            PORTFOLIO_ARCHETYPE_CYCLE[user_index % len(PORTFOLIO_ARCHETYPE_CYCLE)]
        ]
        user = User(
            email=fake.unique.email(),
            full_name=fake.name(),
            risk_profile=_risk_profile_for_archetype(archetype),
        )
        session.add(user)
        session.flush()
        portfolio = Portfolio(user_id=user.id)
        session.add(portfolio)
        session.flush()

        budget = Decimal(rng.randrange(500_000, 2_000_000, 10_000))

        # Portföy, geçmişin ilk günlerinde tek DEPOSIT ile fonlanır.
        all_days = days_by_asset[usdtry_id]
        window = [d for d in all_days if d <= anchor]
        deposit_day = window[rng.randint(0, 9)]
        record_transaction(
            session,
            portfolio.id,
            TransactionType.DEPOSIT,
            transaction_date=_tx_datetime(deposit_day),
            cash_amount_try=budget,
            note="Başlangıç fonlaması",
        )
        tx_count += 1

        time_deposit_events: list[tuple] = []  # (alım günü, yatırılan tutar)

        for asset_class, (weight, pick_count) in archetype.items():
            candidates = assets_by_class.get(asset_class, [])
            if not candidates:
                continue
            picked = rng.sample(candidates, min(pick_count, len(candidates)))
            class_budget = budget * Decimal(str(weight)) * Decimal("0.9")  # %10 pay: komisyon+nakit
            per_asset = class_budget / len(picked)

            for asset in picked:
                asset_days = [d for d in days_by_asset[asset.id] if deposit_day < d <= anchor]
                if not asset_days:
                    continue
                num_buys = rng.randint(1, 3)
                buy_days = sorted(rng.sample(asset_days, min(num_buys, len(asset_days))))
                per_buy = per_asset / len(buy_days)

                for buy_day in buy_days:
                    price = prices[asset.id][buy_day]
                    fx = (
                        _fx_rate_on(prices, days_by_asset, usdtry_id, buy_day)
                        if asset.currency == "USD"
                        else Decimal(1)
                    )
                    quantity = (per_buy / (price * fx)).quantize(
                        QUANTITY_PRECISION[asset.asset_class], rounding=ROUND_DOWN
                    )
                    if quantity <= 0:
                        continue
                    gross = quantity * price * fx
                    fee = (
                        (gross * STOCK_FEE_RATE).quantize(_TRY_QUANT, rounding=ROUND_HALF_UP)
                        if asset.asset_class == AssetClass.STOCK
                        else Decimal(0)
                    )
                    record_transaction(
                        session,
                        portfolio.id,
                        TransactionType.BUY,
                        transaction_date=_tx_datetime(buy_day),
                        asset_id=asset.id,
                        quantity=quantity,
                        price=price,
                        currency=asset.currency,
                        fx_rate_to_try=fx,
                        fee_try=fee,
                    )
                    tx_count += 1
                    if asset.symbol == "MEVDUAT-V":
                        time_deposit_events.append((buy_day, quantity * price))

        # Vadeli mevduat: aylık faiz, INTEREST kaydı olarak (varlığa bağlı değil).
        for start_day, principal in time_deposit_events:
            payment_days = [
                d for d in window if d > start_day and d.day <= 7 and d.month != start_day.month
            ]
            seen_months: set[tuple[int, int]] = set()
            for pay_day in payment_days:
                key = (pay_day.year, pay_day.month)
                if key in seen_months:
                    continue
                seen_months.add(key)
                interest = (principal * TIME_DEPOSIT_MONTHLY_RATE).quantize(
                    _TRY_QUANT, rounding=ROUND_HALF_UP
                )
                record_transaction(
                    session,
                    portfolio.id,
                    TransactionType.INTEREST,
                    transaction_date=_tx_datetime(pay_day),
                    cash_amount_try=interest,
                    note="Vadeli mevduat faizi",
                )
                tx_count += 1

        # ~%30 kullanıcı geçmişin sonlarında kısmi satış yapar (gerçekleşmiş
        # kâr/zarar üretimi için).
        if rng.random() < 0.3:
            # Satış günü ÖNCE seçilir; pozisyon o güne göre hesaplanır. Aksi
            # halde satış, aynı varlığın daha sonraki bir alımını "önceden"
            # satmaya çalışıp defteri tutarsızlaştırabilir.
            late_days = [d for d in window][-15:]
            sell_day = late_days[rng.randrange(len(late_days))]
            quantities = position_as_of(session, portfolio.id, sell_day)
            sellable = [
                (asset_id, qty)
                for asset_id, qty in quantities.items()
                if qty > 0 and asset_id != assets["MEVDUAT-V"].id
            ]
            if sellable:
                asset_id, quantity = sellable[rng.randrange(len(sellable))]
                asset = next(a for a in assets.values() if a.id == asset_id)
                if sell_day not in prices[asset_id]:
                    # Takvim farkı (tatil): önceki fiyatlı güne çekil ve
                    # pozisyonu o güne göre yeniden hesapla. Uygun gün yoksa
                    # miktar 0 kalır ve satış sessizce atlanır.
                    earlier = [d for d in days_by_asset[asset_id] if d <= sell_day]
                    if earlier:
                        sell_day = earlier[-1]
                        quantity = position_as_of(session, portfolio.id, sell_day).get(
                            asset_id, Decimal(0)
                        )
                    else:
                        quantity = Decimal(0)
                fraction = Decimal(str(round(rng.uniform(0.1, 0.4), 4)))
                sell_qty = (quantity * fraction).quantize(
                    QUANTITY_PRECISION[asset.asset_class], rounding=ROUND_DOWN
                )
                if sell_qty > 0:
                    price = prices[asset_id][sell_day]
                    fx = (
                        _fx_rate_on(prices, days_by_asset, usdtry_id, sell_day)
                        if asset.currency == "USD"
                        else Decimal(1)
                    )
                    gross = sell_qty * price * fx
                    fee = (
                        (gross * STOCK_FEE_RATE).quantize(_TRY_QUANT, rounding=ROUND_HALF_UP)
                        if asset.asset_class == AssetClass.STOCK
                        else Decimal(0)
                    )
                    record_transaction(
                        session,
                        portfolio.id,
                        TransactionType.SELL,
                        transaction_date=_tx_datetime(sell_day),
                        asset_id=asset_id,
                        quantity=sell_qty,
                        price=price,
                        currency=asset.currency,
                        fx_rate_to_try=fx,
                        fee_try=fee,
                    )
                    tx_count += 1

        # holdings = defterden türetilir; elle yazım YOK.
        rebuild_holdings(session, portfolio.id)

    session.commit()
    return tx_count
