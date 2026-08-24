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
from datetime import date, datetime, time, timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from faker import Faker
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import AssetClass, RiskProfile, settings
from app.core.security import hash_password
from app.models import Asset, PriceHistory, Transaction, TransactionType
from app.providers.universe import SPEC_BY_SYMBOL
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

# Alım/satımda adet yuvarlaması. Hisse ve döviz tam sayı (lot/birim), diğerleri
# küsuratlı. BOND tam sayıydı — doğrudan tahvil adet bazlı alınır — ama sınıfın
# tamamı artık TEFAS borçlanma araçları fonu (bkz. providers/universe.py) ve
# fonlar küsuratlı alınır; birim fiyatları 0,14 TL mertebesinde olduğundan tam
# sayıya yuvarlamak da gereksiz bir sapma bırakıyordu.
QUANTITY_PRECISION: dict[AssetClass, Decimal] = {
    AssetClass.STOCK: Decimal(1),
    AssetClass.PRECIOUS_METAL: Decimal("0.01"),
    AssetClass.CURRENCY: Decimal(1),
    AssetClass.BOND: Decimal("0.01"),
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

# ÜRÜN SAHİBİ KARARI (Not 5, 2026-08): risk profili artık arketipten BAĞIMSIZ
# ayrı bir sayaçla dönmüyor — "profil önce belirlenir, portföy ona göre
# kurulur, tersine sistem izin vermez" ilkesinin (Not 3/4) dummy veri
# karşılığı olarak her arketip TAM OLARAK bir risk profiline sabit biçimde
# eşlenir (bkz. ARCHETYPE_RISK_PROFILE).
#
# Önceki tasarım (_profile_and_archetype, AK-2.6) profili arketipten bağımsız
# ve farklı hızda döndürüyordu; bu KASITLI olarak uyumsuz kombinasyonlar da
# üretiyordu (ör. CONSERVATIVE profilli %75 hisseli kullanıcı) — amaç, risk
# motorunun uyumsuzluk-uyarısı yolunu dummy veriyle sergileyebilmekti. PO bu
# kararı geri aldı: dummy veri artık gerçekçi/tutarlı olmalı; uyumsuzluk-
# uyarısı yolu zaten kendi birim testleriyle (tests/test_risk_service.py)
# doğrulanıyor, dummy veride bunun için kasıtlı bir bozukluğa gerek yok.
#
# 'growth' (Büyüme) enum'a b26e8dab6ef9 ile eklendi; risk_service onun için
# ayrı sabitler taşıyor (RISK_TARGET_VOLATILITY_BAND, RISK_MAX_CATEGORY_WEIGHT,
# RISK_DEFENSE_FLOOR, RISK_RECEIVER_PREFERENCE_ORDER — hepsinde GROWTH
# anahtarı var). Aşağıdaki eşleme dört arketipi hisse ağırlığına göre artan
# sırada, dört profille (yine artan risk sırasında) BİREBİR eşler; böylece
# GROWTH dahil dört profilin tamamı üretilir ve hiçbir arketip kendi
# profilinin Hisse üst sınırını aşmaz (bkz. tests/test_seed_ledger_determinism.py).
_RISK_PROFILE_ORDER = [
    RiskProfile.CONSERVATIVE,
    RiskProfile.BALANCED,
    RiskProfile.GROWTH,
    RiskProfile.AGGRESSIVE,
]


def _build_archetype_risk_profiles() -> dict[str, RiskProfile]:
    ordered_archetypes = sorted(
        PORTFOLIO_ARCHETYPES,
        key=lambda name: PORTFOLIO_ARCHETYPES[name].get(AssetClass.STOCK, (0.0, 0))[0],
    )
    assert len(ordered_archetypes) == len(
        _RISK_PROFILE_ORDER
    ), "arketip sayısı risk profili sayısıyla eşleşmiyor; eşleme elle güncellenmeli"
    return dict(zip(ordered_archetypes, _RISK_PROFILE_ORDER))


ARCHETYPE_RISK_PROFILE: dict[str, RiskProfile] = _build_archetype_risk_profiles()

# Kullanıcı kimliklerinin tohuma bağlı olması için sabit ad alanı. Değeri
# keyfi ama DEĞİŞMEMELİ: değişirse tüm kullanıcı UUID'leri değişir.
USER_UUID_NAMESPACE = uuid.UUID("6f2a1c7e-9b34-4d51-8a0e-3c5d7e1f2b48")

_TRY_QUANT = Decimal("0.0001")

# --- İşlem çeşitliliği ------------------------------------------------------
#
# Ölçüm (21 Ağustos 2026, 50 kullanıcı): alımlar 250 farklı güne yayılmışken
# satışlar 14 taneydi, hepsi son 15 işlem gününde ve yalnızca 14 kullanıcıda.
# Sonucu: gerçekleşmiş kâr/zarar neredeyse hiç üretilmiyor, işlem geçmişi
# "hep alım" gibi görünüyor ve TWR'in dönem içi davranışı sınanmıyordu.
#
# Eski kısıtın gerekçesi (satış, aynı varlığın SONRAKİ bir alımını önceden
# satmasın) geçerli ama son 15 güne sıkışmayı gerektirmiyordu: pozisyon zaten
# `position_as_of` ile o güne göre hesaplanıyor.
SELL_PROBABILITY = 0.6
MAX_SELLS_PER_USER = 4

# --- Ara nakit hareketleri --------------------------------------------------
#
# Ölçüm: "yatırılan tutar" serisi 20 kullanıcının 20'sinde de DÜZ çıkıyordu —
# her portföy başlangıçta tek DEPOSIT alıp bir daha hiç nakit hareketi
# görmüyordu. Performans grafiğindeki o çizgi hiçbir şey anlatmıyor, TWR'in
# "dış para akışını getiriden ayırma" yeteneği de gösterilemiyordu.
EXTRA_DEPOSIT_PROBABILITY = 0.45
WITHDRAW_PROBABILITY = 0.35
EXTRA_DEPOSIT_RANGE = (Decimal("0.05"), Decimal("0.20"))  # başlangıç bütçesinin oranı
WITHDRAW_RANGE = (Decimal("0.15"), Decimal("0.45"))  # çekilebilir nakdin oranı

# Bu tutarın altındaki çekim demoda görünmez; işlem listesini şişirmeye değmez.
MIN_WITHDRAW_TRY = Decimal("5000")


def _cash_floor_from(session: Session, portfolio_id: uuid.UUID, day: date) -> Decimal:
    """`day` gününden itibaren defterin göreceği EN DÜŞÜK nakit bakiyesi.

    Para çekme bu değerin üstünde olamaz. O günkü bakiyeye bakmak yetmiyor:
    çekimden SONRA gelen alımlar bakiyeyi aşağı çeker ve defter ara bir günde
    negatife düşerdi. Değişmez testi (I2) eskiden yalnızca SON bakiyeye
    baktığı için böyle bir hata sessizce geçerdi; test artık her işlem gününü
    denetliyor ve bu fonksiyon ona uyacak şekilde yazıldı.
    """
    rows = session.execute(
        select(Transaction.transaction_date, Transaction.cash_amount_try)
        .where(Transaction.portfolio_id == portfolio_id)
        .order_by(Transaction.transaction_date)
    ).all()

    running = Decimal(0)
    floor: Decimal | None = None
    for tx_date, cash in rows:
        running += Decimal(str(cash or 0))
        if tx_date.date() >= day:
            floor = running if floor is None else min(floor, running)
    if floor is None:
        # `day`den sonra hiç işlem yok: sınır, o ana kadarki bakiyedir.
        return running
    return floor


def _user_id(user_index: int) -> uuid.UUID:
    """Kullanıcı sırasından deterministik UUID.

    Model varsayılanı `uuid.uuid4` — işletim sisteminin rastgeleliğini kullanır
    ve SEED'den etkilenmez. Sonuç: isimler, portföyler ve işlemler her seed'de
    aynı üretilirken KİMLİKLER değişiyordu. Her `make seed` sonrası elde tutulan
    test kimlikleri ölüyor, arayüzün seçili profili geçersizleşiyor, hata
    raporlarındaki id başka bir kullanıcıya işaret ediyordu.

    uuid5 ad alanı + isim üzerinden hesaplar, yani tohum gibi davranır.
    """
    return uuid.uuid5(USER_UUID_NAMESPACE, f"user-{user_index}")


def _tx_datetime(d) -> datetime:
    return datetime.combine(d, time(hour=11), tzinfo=timezone.utc)


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

    # Modül düzeyinde değil burada: bcrypt özeti pahalı bir hesap ve seed
    # dışında bu modülü import eden hiç kimseye maliyet çıkarmamalı.
    demo_password_hash = hash_password(settings.demo_user_password)

    # AYRI ve KENDİ RNG'sine sahip bir Faker örneği, bilerek. T.C. kimlik
    # numaralarını yukarıdaki `fake`ten üretmek her kullanıcıda bir çağrı daha
    # ekler ve SONRAKİ kullanıcıların e-posta/adlarını kaydırırdı; bu
    # değişikliğin mevcut seed çıktısına dokunmaması gerekiyor.
    #
    # `Faker.seed()` DEĞİL `seed_instance()`: birincisi sınıf düzeyindedir ve
    # tüm örneklerin PAYLAŞTIĞI üreteci sıfırlar — burada çağrılsaydı `fake`in
    # akışını da başa sardırırdı. `seed_instance` bu örneğe kendi Random'ını
    # verir, iki akış tamamen bağımsız olur.
    fake_identity = Faker("tr_TR")
    fake_identity.seed_instance(SEED)
    fake_identity.unique.clear()

    assets, prices, days_by_asset = _load_price_book(session)
    usdtry_id = assets["USDTRY"].id

    # Alım adayları YALNIZCA tutulabilir varlıklar.
    #
    # Endeksler (XU100) fiyatlanıp saklanıyor çünkü kıyaslama onlara dayanıyor,
    # ama satın alınamazlar. Bu süzgeç olmadan seed, BIST 100'ü sıradan bir
    # hisse gibi kullanıcılara dağıtırdı — portföyünde "1.084 adet BIST 100"
    # duran bir kullanıcı hem saçma hem de tüm dağılım/risk hesabını bozardı.
    #
    # Tutulabilirlik `assets` tablosunda değil evren tanımında yaşıyor
    # (`providers/universe.py`); DB'ye bir kolon eklemek yerine oradan
    # okunuyor. Başka bir tüketici de bu bilgiye ihtiyaç duyarsa kolon
    # gerekecek.
    assets_by_class: dict[AssetClass, list[Asset]] = {}
    for asset in assets.values():
        spec = SPEC_BY_SYMBOL.get(asset.symbol)
        if spec is not None and not spec.tradable:
            continue
        assets_by_class.setdefault(asset.asset_class, []).append(asset)
    for asset_list in assets_by_class.values():
        asset_list.sort(key=lambda a: a.symbol)  # determinizm sözlük sırasına bağlı kalmasın

    anchor = settings.anchor_date
    tx_count = 0

    for user_index in range(NUM_USERS):
        archetype_name = PORTFOLIO_ARCHETYPE_CYCLE[user_index % len(PORTFOLIO_ARCHETYPE_CYCLE)]
        archetype = PORTFOLIO_ARCHETYPES[archetype_name]
        user = User(
            id=_user_id(user_index),
            email=fake.unique.email(),
            full_name=fake.name(),
            risk_profile=ARCHETYPE_RISK_PROFILE[archetype_name],
            # Faker'ın tr_TR sağlayıcısı SAĞLAMASI GEÇERLİ bir T.C. kimlik
            # numarası üretir (doğrulandı), dolayısıyla giriş ekranındaki
            # 11 hane + sağlama kontrolü anlamlı bir kapı olur. Faker.seed
            # sabit olduğu için aynı kullanıcı her seed'de aynı numarayı alır
            # — ekip numarayı ezberler, seed tazelense de bozulmaz.
            national_id=fake_identity.unique.ssn(),
            # Tüm demo kullanıcıları aynı şifreyi paylaşır ve özet BİR KEZ
            # hesaplanır: 50 ayrı bcrypt çağrısı seed'e ~15 saniye eklerdi ve
            # 50 farklı şifreyi ezberlemenin demoya hiçbir katkısı yok.
            # Doğrulama yolu buna rağmen tamamen gerçek (bkz. auth_service).
            password_hash=demo_password_hash,
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

        # --- Kısmi satışlar: pencerenin TAMAMINA yayılır -------------------
        #
        # Satış günleri ARTAN sırada işlenir. Sıra önemli: `position_as_of`
        # oturumdan okuyor, dolayısıyla her hesap kendinden önceki satışları
        # görür. Ters sırada işlense aynı lotu iki kez satmak mümkün olurdu.
        if rng.random() < SELL_PROBABILITY:
            aday_gunler = [d for d in window if d > deposit_day]
            if aday_gunler:
                kac = rng.randint(1, MAX_SELLS_PER_USER)
                for sell_day in sorted(rng.sample(aday_gunler, min(kac, len(aday_gunler)))):
                    quantities = position_as_of(session, portfolio.id, sell_day)
                    sellable = [
                        (asset_id, qty)
                        for asset_id, qty in quantities.items()
                        if qty > 0 and asset_id != assets["MEVDUAT-V"].id
                    ]
                    if not sellable:
                        continue
                    asset_id, quantity = sellable[rng.randrange(len(sellable))]
                    asset = next(a for a in assets.values() if a.id == asset_id)
                    if sell_day not in prices[asset_id]:
                        # Takvim farkı (tatil): önceki fiyatlı güne çekil ve
                        # pozisyonu o güne göre yeniden hesapla. Uygun gün
                        # yoksa miktar 0 kalır ve satış sessizce atlanır.
                        earlier = [d for d in days_by_asset[asset_id] if d <= sell_day]
                        if not earlier:
                            continue
                        sell_day = earlier[-1]
                        quantity = position_as_of(session, portfolio.id, sell_day).get(
                            asset_id, Decimal(0)
                        )
                    fraction = Decimal(str(round(rng.uniform(0.1, 0.4), 4)))
                    sell_qty = (quantity * fraction).quantize(
                        QUANTITY_PRECISION[asset.asset_class], rounding=ROUND_DOWN
                    )
                    if sell_qty <= 0:
                        continue
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

        # --- Ara nakit hareketleri -----------------------------------------
        #
        # Ek yatırma nakdi ARTIRIR, dolayısıyla defteri hiçbir günde riske
        # atmaz; sırası da önemsizdir.
        if rng.random() < EXTRA_DEPOSIT_PROBABILITY:
            aday_gunler = [d for d in window if d > deposit_day]
            if aday_gunler:
                gun = aday_gunler[rng.randrange(len(aday_gunler))]
                oran = Decimal(str(round(rng.uniform(*map(float, EXTRA_DEPOSIT_RANGE)), 4)))
                tutar = (budget * oran).quantize(_TRY_QUANT, rounding=ROUND_HALF_UP)
                record_transaction(
                    session,
                    portfolio.id,
                    TransactionType.DEPOSIT,
                    transaction_date=_tx_datetime(gun),
                    cash_amount_try=tutar,
                    note="Ek yatırma",
                )
                tx_count += 1

        # Çekim EN SON işlenir ve `_cash_floor_from` ile boyutlandırılır:
        # o günkü bakiyeye göre değil, o günden sonra defterin göreceği EN
        # DÜŞÜK bakiyeye göre. Aksi halde çekimden sonraki bir alım defteri
        # ara bir günde eksiye düşürürdü.
        if rng.random() < WITHDRAW_PROBABILITY:
            aday_gunler = [d for d in window if d > deposit_day]
            if aday_gunler:
                gun = aday_gunler[rng.randrange(len(aday_gunler))]
                taban = _cash_floor_from(session, portfolio.id, gun)
                if taban > MIN_WITHDRAW_TRY:
                    oran = Decimal(str(round(rng.uniform(*map(float, WITHDRAW_RANGE)), 4)))
                    tutar = (taban * oran).quantize(_TRY_QUANT, rounding=ROUND_HALF_UP)
                    if tutar >= MIN_WITHDRAW_TRY:
                        record_transaction(
                            session,
                            portfolio.id,
                            TransactionType.WITHDRAW,
                            transaction_date=_tx_datetime(gun),
                            cash_amount_try=-tutar,
                            note="Para çekme",
                        )
                        tx_count += 1

        # holdings = defterden türetilir; elle yazım YOK.
        rebuild_holdings(session, portfolio.id)

    session.commit()
    return tx_count
