"""Sentetik kullanıcılar + İŞLEM DEFTERİ üretir; holdings DEFTERDEN türetilir.

Eski üreticiden temel farklar:
- Her portföy önce DEPOSIT ile fonlanır; her alım/satımın nakit ayağı yazılır.
  Defter her an dengelidir (nakit = SUM(cash_amount_try) >= 0).
- İşlem tarihleri fiyatın gerçekten VAR OLDUĞU günlere hizalanır (işlem
  günleri); hafta sonuna denk alım artık mümkün değildir.
- NAKİT satın alınmaz: bütçenin nakit payı harcanmadan defterde serbest
  bakiye olarak kalır (bkz. providers/universe.py — CASH altında varlık yok).
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

from app.core.config import (
    ASSET_QUANTITY_PRECISION,
    AssetClass,
    RiskProfile,
    risk_profile_for_survey_score,
    settings,
    survey_score_band,
)
from app.core.security import hash_password
from app.models import Asset, PriceHistory, Transaction, TransactionType
from app.providers.universe import SPEC_BY_SYMBOL
from app.services.advice_eligibility import asset_risk_level, is_asset_advice_allowed
from app.services.ledger_service import position_as_of, rebuild_holdings, record_transaction
from data.anchor import resolve_anchor_date
from data.names import ad_soyad, eposta

SEED = 42
NUM_USERS = 50
# Test/mutabakat sözleşmesi: kullanıcı başına işlem GÖRMÜŞ varlık sayısı aralığı.
#
# ALT SINIR 5'TEN 1'E INDI. Portföyler artık anket puanının izin verdiği
# varlıklardan kuruluyor (bkz. `_uygun_arketip`) ve en düşük puan (1)
# yalnızca TEK varlığı açıyor: para piyasası fonu IOO. Bu bir eksiklik
# değil, kuralın kendisi — 1 puanlık kullanıcının alabileceği başka bir şey
# yok. Alt sınırı 5'te tutmak, seed'i kendi uygunluk kuralını ihlal etmeye
# zorlardı.
MIN_HOLDINGS_PER_USER = 1
MAX_HOLDINGS_PER_USER = 15

# Hisse alım/satım komisyonu (brüt tutarın oranı); diğer sınıflarda 0.
STOCK_FEE_RATE = Decimal("0.0015")

# Alım/satımda adet yuvarlaması. Hisse ve döviz tam sayı (lot/birim), diğerleri
# küsuratlı. BOND tam sayıydı — doğrudan tahvil adet bazlı alınır — ama sınıfın
# tamamı artık TEFAS borçlanma araçları fonu (bkz. providers/universe.py) ve
# fonlar küsuratlı alınır; birim fiyatları 0,14 TL mertebesinde olduğundan tam
# sayıya yuvarlamak da gereksiz bir sapma bırakıyordu.
# Tanım `core/config.ASSET_QUANTITY_PRECISION`'a taşındı: işlem ucu da aynı
# yuvarlamayı kullanıyor ve iki kopya olsaydı seed ile kullanıcı emirleri
# farklı hassasiyetle yazılabilirdi.
QUANTITY_PRECISION = ASSET_QUANTITY_PRECISION

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


def _uygun_arketip(
    archetype: dict[AssetClass, tuple[float, int]],
    assets_by_class: dict[AssetClass, list[Asset]],
    survey_score: int,
) -> dict[AssetClass, tuple[float, int, list[Asset]]]:
    """Arketipi kullanıcının ANKET PUANINA göre süzer ve ağırlıkları yeniden
    normalleştirir.

    Ürün Sahibi'nin ilkesi (Not 3/4): "profil önce belirlenir, portföy ona
    göre kurulur, tersine sistem izin vermez." Süzgeç olmadan bu ilke dummy
    veride ihlal ediliyordu: HER arketipte hisse, kıymetli maden ve döviz
    vardı, oysa muhafazakâr bandın (1-2) izin verdiği tek sınıf tahvil,
    dengeli bandın (3-4) izin vermediği tek sınıf ise hisse. Ölçüldü:
    50 kullanıcının 31'i puanının izin vermediği bir varlık tutuyordu.

    Süzme VARLIK düzeyinde yapılır, sınıf düzeyinde değil: Büyüme bandı (5)
    hisse sınıfını açar ama ABD hisselerini (6) ve serbest fonu (7) açmaz.
    Sınıf düzeyinde süzülseydi büyüme profilli kullanıcı AAPL tutabilirdi.

    Kalan ağırlıklar ORANTILI dağıtılır (nakit dahil): elenen sınıfın payını
    tamamen nakde yığmak arketipin karakterini bozardı — `cash_heavy`
    zaten nakit ağırlıklı, `diversified` ise çeşitlendirilmiş kalmalı.
    Orantılı dağıtım hayatta kalan sınıfların BİRBİRİNE göre oranını
    koruyor.

    Dönen üçlü: `(ağırlık, seçilecek adet, uygun adaylar)`. Nakit sınıfı
    listesi boş gelir — nakit satın alınmaz, harcanmayan bakiyedir.
    """
    kalan: dict[AssetClass, tuple[float, int, list[Asset]]] = {}
    for asset_class, (weight, pick_count) in archetype.items():
        if asset_class is AssetClass.CASH:
            kalan[asset_class] = (weight, 0, [])
            continue
        adaylar = [
            a
            for a in assets_by_class.get(asset_class, [])
            if is_asset_advice_allowed(a.symbol, a.asset_class, survey_score)
        ]
        if adaylar:
            kalan[asset_class] = (weight, pick_count, adaylar)

    toplam = sum(w for w, _, _ in kalan.values())
    if toplam <= 0:  # pragma: no cover - her bantta en az bir sınıf kalıyor
        return kalan
    return {ac: (w / toplam, n, lst) for ac, (w, n, lst) in kalan.items()}


def _tepe_kademe(
    uygun_archetype: dict[AssetClass, tuple[float, int, list["Asset"]]],
) -> int:
    """Kullanıcının erişebildiği EN ÜST uygunluk kademesi.

    Puanın kendisi değil, o puanla gerçekten alınabilen varlıkların en üst
    seviyesi. İkisi 7 puanda ayrışabilir: puan 7'dir ama arketipte serbest
    fonun bulunduğu sınıf yoksa tepe 6'da kalır.
    """
    seviyeler = [
        asset_risk_level(a.symbol, a.asset_class)
        for _, _, adaylar in uygun_archetype.values()
        for a in adaylar
    ]
    return max(seviyeler, default=1)


def _tepe_temsil_edilsin(
    picked: list["Asset"],
    candidates: list["Asset"],
    tepe: int,
    rng: random.Random,
) -> list["Asset"]:
    """Sınıfta kullanıcının tepe kademesinden varlık varsa, en az biri seçilsin.

    NEDEN GEREKLİ. Süzgeç doğru çalışıyordu ama seçim aday havuzunda düzgün
    dağılımlıydı ve üst kademeler havuzda çok azınlıkta: hisse sınıfında 101
    yerli varlığa karşı 21 ABD hissesi ve TEK bir serbest fon var. Konsantre
    arketip 4 hisse seçiyor, dolayısıyla üst kademeler istatistiksel olarak
    kayboluyordu. Ölçüldü: 6-7 puanlı 13 kullanıcının yalnızca 5'i herhangi
    bir yabancı varlık tutuyordu ve `BHE`'yi (seviye 7, evrendeki tek serbest
    fon) **hiç kimse** tutmuyordu.

    Sonuç: 5, 6 ve 7 puanlı portföyler ekranda ayırt edilemiyordu — yani
    uygunluk merdiveninin tepesi demoda hiç görünmüyordu.

    Aşağı kademelerde bu neredeyse işlemsizdir: 4 puanlı kullanıcının tepesi
    kıymetli madendir ve o sınıfta zaten hemen her varlık o kademededir.
    Isırdığı yer yalnızca 6 ve 7.

    Değiştirme SON sırayı hedefler (`picked[-1]`), böylece `rng.sample`'ın
    ürettiği sıranın başı korunur ve determinizm bozulmaz.
    """
    tepedekiler = [a for a in candidates if asset_risk_level(a.symbol, a.asset_class) == tepe]
    if not tepedekiler or any(a in tepedekiler for a in picked):
        return picked
    yeni = rng.choice(tepedekiler)
    if yeni in picked:  # pragma: no cover - üstteki `any` bunu zaten eler
        return picked
    return picked[:-1] + [yeni]


def _survey_score(user_index: int, profile: RiskProfile) -> int:
    """Kullanıcının anket puanı: profilin bandı içinde deterministik dağılım.

    Profil arketipten geliyor, arketip de `user_index % 4` ile seçiliyor —
    yani aynı profildeki kullanıcıların indeksleri 4'ün katları kadar
    aralıklı. Doğrudan `user_index % bant` alınsaydı hepsi bandın AYNI
    ucuna düşerdi (0, 4, 8 ... hepsi %2 = 0) ve 1, 3, 6 puanları seed'de
    hiç görünmezdi. Önce tur sayısına bölmek bandı gerçekten tarıyor.

    Böylece yedi puanın yedisi de demo verisinde temsil ediliyor ve uygunluk
    merdiveninin her kademesi elle puan değiştirmeden görülebiliyor.
    """
    alt, ust = survey_score_band(profile)
    return alt + (user_index // len(PORTFOLIO_ARCHETYPE_CYCLE)) % (ust - alt + 1)


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

    # Modül düzeyinde değil burada: bcrypt özeti pahalı bir hesap ve seed
    # dışında bu modülü import eden hiç kimseye maliyet çıkarmamalı.
    demo_password_hash = hash_password(settings.demo_user_password)

    # Faker YALNIZCA T.C. kimlik numarası için kaldı. Ad ve e-posta artık
    # `data/names.py`ten geliyor (Faker'ın tr_TR sağlayıcısı ünvanlı/arkaik
    # adlar üretiyordu ve e-postayı addan bağımsız seçiyordu — gerekçe orada).
    #
    # `Faker.seed()` DEĞİL `seed_instance()`: birincisi sınıf düzeyindedir ve
    # tüm Faker örneklerinin PAYLAŞTIĞI üreteci sıfırlar; başka bir modül aynı
    # süreçte Faker kullanırsa bu örneğin akışını da kaydırırdı.
    # `seed_instance` bu örneğe kendi Random'ını verir, akış yalıtılmış olur.
    # (Doğrulandı: ad/e-posta çağrıları kaldırıldığında üretilen kimlik
    # numaraları değişmiyor — ekibin ezberlediği giriş bilgileri korunuyor.)
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

    anchor = resolve_anchor_date(session)
    tx_count = 0

    for user_index in range(NUM_USERS):
        archetype_name = PORTFOLIO_ARCHETYPE_CYCLE[user_index % len(PORTFOLIO_ARCHETYPE_CYCLE)]
        archetype = PORTFOLIO_ARCHETYPES[archetype_name]
        # TEK kaynak: hem User kaydına yazılan puan hem portföyü süzen puan
        # buradan geliyor. İki ayrı çağrı olsaydı biri değiştiğinde diğeri
        # sessizce geride kalır ve seed kendi kuralını ihlal ederdi.
        survey_score = _survey_score(user_index, ARCHETYPE_RISK_PROFILE[archetype_name])
        full_name = ad_soyad(user_index)
        user = User(
            id=_user_id(user_index),
            email=eposta(full_name),
            full_name=full_name,
            risk_profile=ARCHETYPE_RISK_PROFILE[archetype_name],
            # Anket puanı YETKİLİ alan, profil ondan türer. Seed'de sıra
            # tersine işliyor (arketip -> profil -> bant içinde puan) çünkü
            # portföyün yapısı arketiple belirleniyor; sonuçta ikisi yine
            # tutarlı: `risk_profile_for_survey_score(puan)` aynı profili
            # verir (tests/test_seed_ledger_determinism.py bunu kilitliyor).
            risk_survey_score=survey_score,
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

        # Portföy, kullanıcının anket puanının izin verdiği varlıklardan
        # kurulur (bkz. `_uygun_arketip`). Puan burada zaten hesaplanmış
        # durumda; User kaydına yazılan değerle AYNI olmalı, yoksa portföy
        # kullanıcının beyanına uymayan bir puana göre kurulur.
        uygun_archetype = _uygun_arketip(archetype, assets_by_class, survey_score)
        tepe = _tepe_kademe(uygun_archetype)

        for asset_class, (weight, pick_count, candidates) in uygun_archetype.items():
            # NAKİT SATIN ALINMAZ — harcanmayan bakiyedir.
            #
            # `AssetClass.CASH` altında artık varlık yok (bkz. universe.py):
            # bütçenin nakit payı hiç harcanmaz ve defterdeki serbest bakiye
            # olarak kalır. Portföy özeti onu `cash_balance_as_of` ile okuyup
            # nakit dilimine ekliyor, yani temsil için bir varlığa gerek yok.
            if asset_class is AssetClass.CASH:
                continue
            picked = rng.sample(candidates, min(pick_count, len(candidates)))
            picked = _tepe_temsil_edilsin(picked, candidates, tepe, rng)
            # Ağırlığın TAMAMI harcanır. Eskiden 0.9 ile çarpılıyordu ("%10 pay:
            # komisyon+nakit") çünkü nakit de bir varlık gibi satın alınıyordu
            # ve ayrıca pay ayırmak gerekiyordu. Artık nakit payı arketipte
            # açıkça yazılı, dolayısıyla ikinci bir kesintiye gerek yok —
            # ağırlıklar toplamı 1.0 ve ekrandaki dağılım arketiple birebir
            # örtüşüyor. Komisyonlar nakit bakiyesinden karşılanır.
            class_budget = budget * Decimal(str(weight))
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
                    sellable = [(asset_id, qty) for asset_id, qty in quantities.items() if qty > 0]
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

    # Demo personası döngünün DIŞINDA, en sonda: ana döngünün `rng` akışına
    # dokunmuyor, dolayısıyla 0-49 arasındaki kullanıcılar bit bit aynı kalıyor.
    tx_count += _seed_demo_persona(
        session,
        assets,
        prices,
        days_by_asset,
        usdtry_id,
        anchor,
        national_id=fake_identity.unique.ssn(),
        password_hash=demo_password_hash,
    )

    session.commit()
    return tx_count


# --- Demo personası ---------------------------------------------------------
#
# ELLE KURULMUŞ 51. KULLANICI. Sunum/demo videolarında hangi hesaba girileceği
# şansa bırakılmasın diye var: dört varlık sınıfının dördü de, serbest nakit,
# döviz cinsi bir varlık ve haberi olan BIST şirketleri tek portföyde.
#
# NEDEN 51. SIRADA. Mevcut 50 kullanıcıdan biri elle şekillendirilseydi o
# indeksin arketipi/puanı değişir, `_survey_score` dağılımı kayar ve seed'in
# bütün dağılım testleri yeniden yazılmak zorunda kalırdı. Sona eklenince
# 0-49 arasındaki UUID'ler, portföyler ve dağılımlar HİÇ kıpırdamıyor.
#
# NEDEN AGRESİF (puan 6). Uygunluk merdiveni (`advice_eligibility`) hisseyi
# ancak 5. puanda açıyor; ölçüldü: puan 3 iki sınıf (12 varlık), puan 4 üç
# sınıf (17 varlık), puan 5+ dört sınıf (139 varlık). Yani dengeli bir persona
# HİÇ hisse tutamaz — tanıtım dosyasındaki manşet senaryo ("X şirketinin son
# çeyreği portföyümü nasıl etkiler") çalışmaz, çünkü personanın şirketi yoktur.
#
# AĞIRLIKLAR PROFİLE UYGUN. Merdiven neyin TUTULABİLECEĞİNİ söyler, ne
# tutulması gerektiğini değil; izin verilenden düşük riskli varlık tutmak
# uyumsuzluk değildir. Sepet, agresif profilin kategori üst sınırlarının
# altında kalıyor (hisse %35 ≤ %85, maden %20 ≤ %35, döviz %20 ≤ %40,
# tahvil %15 ≤ %50, nakit %10 ≤ %25) ve yoğunlaşma nedenini tetiklemiyor
# (HHI 0,14 < 0,25; en ağır varlık %18 < %35). Bu bilinçli: yoğunlaşma
# uyarısı yalnızca risk YÜKSEK çıktığında sebep olarak gösteriliyor ve
# istenen şey çeşitlilik — ikisi aynı portföyde birbirini götürür.
#
# RASTGELELİK YOK. Ana döngü `rng` kullanıyor; persona kullanmıyor. Alım
# günleri pencere içindeki ORANLA seçiliyor, dolayısıyla ankraj kayınca da
# aynı şekil korunuyor ve persona ana döngünün rastgele akışına dokunmuyor.
DEMO_PERSONA_INDEX = NUM_USERS
TOPLAM_KULLANICI = NUM_USERS + 1

DEMO_PERSONA_SURVEY_SCORE = 6
DEMO_PERSONA_BUDGET = Decimal("1250000")

# (sembol, bütçe payı, alım günlerinin pencere içindeki konumu)
#
# ASELS iki kez alınıyor: ağırlıklı ortalama maliyetin ve çok lotlu bir
# pozisyonun ekranda görünmesi için. RAG doküman kümesinde en çok belgesi
# olan şirket de o (üç doküman), yani haber senaryosu en sağlam onda çalışır.
# AAPL USD cinsi: portföy değerlemesindeki kur çevrimi (AK 5.7) ekranda
# gerçekten görünür olsun diye.
DEMO_PERSONA_SEPET: tuple[tuple[str, str, tuple[float, ...]], ...] = (
    ("APT", "0.15", (0.08,)),
    ("XAUTRY", "0.20", (0.10,)),
    ("USDTRY", "0.12", (0.12,)),
    ("ASELS", "0.18", (0.15, 0.55)),
    ("THYAO", "0.09", (0.20,)),
    ("AAPL", "0.08", (0.30,)),
    ("EURTRY", "0.08", (0.35,)),
)
# Payların toplamı 0,90; kalan %10 hiç harcanmayıp serbest nakit olarak kalır
# (nakit satın alınmaz — bkz. universe.py).

# Geçmişte kısmi satış: gerçekleşmiş kâr/zarar ve dolu bir işlem geçmişi
# olmadan "işlemlerim" ekranı boş bir liste gibi görünüyor.
DEMO_PERSONA_SATIS = ("THYAO", "0.35", 0.75)


def _konum_gunu(gunler: list[date], oran: float) -> date:
    """Gün listesinde orana karşılık gelen gün. Liste boşsa çağrılmamalı."""
    return gunler[min(int(len(gunler) * oran), len(gunler) - 1)]


def _seed_demo_persona(
    session: Session,
    assets: dict[str, Asset],
    prices: dict,
    days_by_asset: dict,
    usdtry_id,
    anchor: date,
    national_id: str,
    password_hash: str,
) -> int:
    """Elle kurulmuş demo personasını yazar; üretilen işlem sayısını döndürür."""
    from app.models import Portfolio, User

    full_name = ad_soyad(DEMO_PERSONA_INDEX)
    user = User(
        id=_user_id(DEMO_PERSONA_INDEX),
        email=eposta(full_name),
        full_name=full_name,
        risk_profile=risk_profile_for_survey_score(DEMO_PERSONA_SURVEY_SCORE),
        risk_survey_score=DEMO_PERSONA_SURVEY_SCORE,
        national_id=national_id,
        password_hash=password_hash,
    )
    session.add(user)
    session.flush()
    portfolio = Portfolio(user_id=user.id)
    session.add(portfolio)
    session.flush()

    window = [d for d in days_by_asset[usdtry_id] if d <= anchor]
    if not window:
        raise RuntimeError("Demo personası için fiyat penceresi boş")
    deposit_day = window[0]

    tx_count = 0
    record_transaction(
        session,
        portfolio.id,
        TransactionType.DEPOSIT,
        transaction_date=_tx_datetime(deposit_day),
        cash_amount_try=DEMO_PERSONA_BUDGET,
        note="Başlangıç fonlaması",
    )
    tx_count += 1

    for symbol, pay, konumlar in DEMO_PERSONA_SEPET:
        asset = assets.get(symbol)
        if asset is None:
            # Evrenden bir sembol çıkarılmışsa persona sessizce eksilir ama
            # seed çökmez; eksik varlık `scripts/data_doctor` ile görülür.
            continue
        asset_days = [d for d in days_by_asset[asset.id] if deposit_day < d <= anchor]
        if not asset_days:
            continue
        per_buy = DEMO_PERSONA_BUDGET * Decimal(pay) / len(konumlar)

        for oran in konumlar:
            buy_day = _konum_gunu(asset_days, oran)
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

    satis_sembol, satis_oran, satis_konum = DEMO_PERSONA_SATIS
    satis_asset = assets.get(satis_sembol)
    if satis_asset is not None:
        gunler = [d for d in days_by_asset[satis_asset.id] if d <= anchor]
        sell_day = _konum_gunu(gunler, satis_konum)
        elde = position_as_of(session, portfolio.id, sell_day).get(satis_asset.id, Decimal(0))
        sell_qty = (elde * Decimal(satis_oran)).quantize(
            QUANTITY_PRECISION[satis_asset.asset_class], rounding=ROUND_DOWN
        )
        if sell_qty > 0:
            price = prices[satis_asset.id][sell_day]
            gross = sell_qty * price
            record_transaction(
                session,
                portfolio.id,
                TransactionType.SELL,
                transaction_date=_tx_datetime(sell_day),
                asset_id=satis_asset.id,
                quantity=sell_qty,
                price=price,
                currency=satis_asset.currency,
                fx_rate_to_try=Decimal(1),
                fee_try=(gross * STOCK_FEE_RATE).quantize(_TRY_QUANT, rounding=ROUND_HALF_UP),
            )
            tx_count += 1

    rebuild_holdings(session, portfolio.id)
    return tx_count
