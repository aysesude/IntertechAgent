from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import RISK_MAX_CATEGORY_WEIGHT, AssetClass, settings
from app.core.security import verify_password
from app.models import Holding, PriceHistory, User
from app.services.ledger_service import cash_balance_as_of
from data.generate_dummy import (
    MAX_HOLDINGS_PER_USER,
    MIN_HOLDINGS_PER_USER,
    NUM_USERS,
)
from data.generate_dummy import (
    main as generate_dummy_main,
)


def test_generate_dummy_creates_expected_data(engine):
    generate_dummy_main()

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(User)) == NUM_USERS

        holding_counts = (
            session.execute(
                select(func.count()).select_from(Holding).group_by(Holding.portfolio_id)
            )
            .scalars()
            .all()
        )
        assert len(holding_counts) == NUM_USERS
        assert all(MIN_HOLDINGS_PER_USER <= c <= MAX_HOLDINGS_PER_USER for c in holding_counts)

        # quantity=0 satırlar (tamamen satılmış pozisyon) tasarım gereği kalabilir;
        # negatif miktar ise her koşulda defter hatasıdır.
        assert (
            session.scalar(select(func.count()).select_from(Holding).where(Holding.quantity < 0))
            == 0
        )
        assert (
            session.scalar(
                select(func.count()).select_from(PriceHistory).where(PriceHistory.close_price <= 0)
            )
            == 0
        )


def test_generate_dummy_is_deterministic(engine):
    # Not: asset_id her main() cagrisinda yeniden olusturulan varliklarin
    # seed'lenmemis (uuid.uuid4()) birincil anahtaridir, bu yuzden calismalar
    # arasi kalici degildir; karsilastirma icin varligin sembolu kullanilir.
    generate_dummy_main()
    with Session(engine) as session:
        first_user = session.execute(select(User).order_by(User.email).limit(1)).scalar_one()
        first_run_holdings = sorted(
            (h.asset.symbol, str(h.quantity), str(h.avg_cost_price))
            for h in first_user.portfolio.holdings
        )

    generate_dummy_main()
    with Session(engine) as session:
        same_user = session.execute(select(User).order_by(User.email).limit(1)).scalar_one()
        assert same_user.email == first_user.email
        second_run_holdings = sorted(
            (h.asset.symbol, str(h.quantity), str(h.avg_cost_price))
            for h in same_user.portfolio.holdings
        )

    assert first_run_holdings == second_run_holdings


def test_generate_dummy_risk_profile_never_mismatches_stock_weight(engine):
    """Not 3'ün dummy veri karşılığı: hiçbir üretilen kullanıcı, kendi risk
    profilinin Hisse üst sınırını aşan bir portföye sahip olmamalı."""
    generate_dummy_main()

    with Session(engine) as session:
        users = session.execute(select(User)).scalars().all()
        assert users  # NUM_USERS>0 olduğu zaten başka testte doğrulanıyor

        for user in users:
            holdings = user.portfolio.holdings
            # Maliyet bazlı (avg_cost_price), risk_service'in güncel fiyat
            # bazlı hesabıyla birebir aynı değil ama arketip hedeflerinin
            # gerçekten uygulandığını doğrulamak için yeterince yakın —
            # asıl nokta nakit dahil TOPLAM üzerinden oranlamak (aksi halde
            # yatırılmayan %10 komisyon/nakit payı hisse oranını yapay
            # olarak şişirir).
            holdings_value = sum(
                (h.quantity * h.avg_cost_price for h in holdings if h.quantity > 0),
                start=0,
            )
            cash = cash_balance_as_of(session, user.portfolio.id)
            total_value = holdings_value + cash
            if total_value <= 0:
                continue
            stock_value = sum(
                (
                    h.quantity * h.avg_cost_price
                    for h in holdings
                    if h.quantity > 0 and h.asset.asset_class == AssetClass.STOCK
                ),
                start=0,
            )
            stock_weight = stock_value / total_value
            limit = RISK_MAX_CATEGORY_WEIGHT[user.risk_profile][AssetClass.STOCK]
            # Tolerans: ARCHETYPE_RISK_PROFILE eşlemesi arketipin NOMİNAL
            # hisse ağırlığını profil sınırıyla karşılaştırır
            # (tests/test_seed_ledger_determinism.py bunu doğrular). Gerçek
            # üretimde işlem yuvarlaması (ROUND_DOWN), bazı varlıkların
            # geçerli işlem günü olmadığı için atlanması ve kısmi SELL
            # senaryoları gerçekleşen ağırlığı nominalden birkaç puan
            # saptırabilir; küçük bir tolerans bu gürültüyü tolere ederken
            # gerçek bir profil/portföy uyumsuzluğunu (asıl önlemek
            # istediğimiz hata) yine de yakalar.
            tolerance = Decimal("0.03")
            assert stock_weight <= limit + tolerance, (
                f"{user.email}: hisse ağırlığı {stock_weight:.2%}, "
                f"{user.risk_profile.value} profilinin sınırı {limit:.0%} "
                f"(tolerans dahil {limit + tolerance:.0%})"
            )


def test_fr_0_seeded_users_can_log_in(engine):
    """Seed her kullanıcıya giriş yapabileceği bir kimlik vermeli (FR-0).

    Üç şey birden doğrulanıyor:
    1. T.C. kimlik numarası SAĞLAMASI GEÇERLİ — giriş ekranındaki 11 hane +
       sağlama kontrolü anlamlı bir kapı olsun diye.
    2. Numaralar benzersiz — `users.national_id` UNIQUE, çakışma seed'i düşürür.
    3. Ortak şifre gerçekten çalışıyor — özet doğru hesaplanmış olmalı;
       `hash_password` çağrısının unutulması ya da yanlış değerin özetlenmesi
       ancak burada yakalanır.
    """
    generate_dummy_main()

    with Session(engine) as session:
        users = session.execute(select(User)).scalars().all()

        assert all(u.national_id for u in users), "her kullanıcının kimlik numarası olmalı"
        assert len({u.national_id for u in users}) == len(users), "numaralar benzersiz olmalı"
        assert all(_gecerli_tckn(u.national_id) for u in users), "sağlama tutmalı"

        # Şifre doğrulama yolu uçtan uca çalışmalı.
        ornek = users[0]
        assert verify_password(settings.demo_user_password, ornek.password_hash)
        assert not verify_password("yanlis-sifre", ornek.password_hash)


def _gecerli_tckn(numara: str) -> bool:
    """T.C. kimlik numarası sağlama algoritması.

    10. hane: (tek sıradakilerin toplamı × 7 − çift sıradakilerin toplamı) mod 10
    11. hane: ilk on hanenin toplamı mod 10
    İlk hane 0 olamaz.
    """
    if len(numara) != 11 or not numara.isdigit() or numara[0] == "0":
        return False
    hane = [int(k) for k in numara]
    onuncu = ((sum(hane[0:9:2]) * 7) - sum(hane[1:8:2])) % 10
    onbirinci = sum(hane[:10]) % 10
    return hane[9] == onuncu and hane[10] == onbirinci


def test_hicbir_kullanici_anket_puaninin_ustunde_varlik_tutmuyor(engine):
    """Ürün Sahibi ilkesi (Not 3/4): "profil önce belirlenir, portföy ona göre
    kurulur, tersine sistem izin vermez."

    Süzgeç eklenmeden önce ölçülen: 50 kullanıcının **31'i** puanının izin
    vermediği bir varlık tutuyordu. Sebebi yapısaldı, rastlantı değil — DÖRT
    arketipin dördünde de hisse, kıymetli maden ve döviz vardı, oysa
    muhafazakâr bandın (1-2) izin verdiği tek sınıf tahvil, dengeli bandın
    (3-4) izin vermediği tek sınıf hisse. Yani muhafazakâr ve dengeli
    kullanıcıların HİÇBİRİ uyumlu olamıyordu.

    Süzme VARLIK düzeyinde olmalı, sınıf düzeyinde değil: büyüme bandı (5)
    hisse sınıfını açar ama ABD hisselerini (6) ve serbest fonu (7) açmaz.
    Sınıf düzeyinde süzülseydi bu test yine geçerdi ama büyüme profilli
    kullanıcı AAPL tutuyor olurdu.
    """
    from app.services.advice_eligibility import is_asset_advice_allowed

    generate_dummy_main()

    with Session(engine) as session:
        users = session.execute(select(User)).scalars().all()
        assert users

        ihlaller: list[str] = []
        for user in users:
            assert user.risk_survey_score is not None, f"{user.email}: anket puanı yok"
            for holding in user.portfolio.holdings:
                if holding.quantity <= 0:
                    continue
                asset = holding.asset
                if not is_asset_advice_allowed(
                    asset.symbol, asset.asset_class, user.risk_survey_score
                ):
                    ihlaller.append(f"puan {user.risk_survey_score} -> {asset.symbol}")

        assert not ihlaller, f"puanının üstünde varlık tutan kullanıcılar: {ihlaller[:10]}"


def test_dusuk_puanli_kullanicinin_portfoyu_daralir(engine):
    """Merdivenin demo verisinde GÖRÜNÜR olduğunu kilitler.

    Uygunluk kuralının işe yaradığının kanıtı, düşük puanlı kullanıcının
    portföyünün gerçekten dar olmasıdır. Bu test olmasaydı süzgeç sessizce
    devre dışı kalabilir ve bir önceki test yine geçerdi (hiç ihlal yok
    demek, hiç kısıt yok demek değildir — ama kısıt hiç ısırmıyorsa süzgeç
    ölü koddur).

    En düşük puan (1) yalnızca para piyasası fonunu açıyor; en yüksek puan
    (7) evrenin tamamını. Aradaki farkın portföy çeşitliliğine yansıması
    gerekir.
    """
    generate_dummy_main()

    with Session(engine) as session:
        users = session.execute(select(User)).scalars().all()

        def sinif_sayisi(puan: int) -> int:
            eslesen = [u for u in users if u.risk_survey_score == puan]
            assert eslesen, f"seed'de {puan} puanlı kullanıcı yok"
            return max(
                len({h.asset.asset_class for h in u.portfolio.holdings if h.quantity > 0})
                for u in eslesen
            )

        assert sinif_sayisi(1) == 1, "1 puanlı kullanıcı yalnızca tahvil sınıfı tutabilmeli"
        assert sinif_sayisi(1) < sinif_sayisi(5), "merdiven portföy çeşitliliğine yansımıyor"


def test_kullanicinin_tepe_kademesi_portfoyunde_gorunur(engine):
    """Uyumluluk YETMEZ: üst kademe gerçekten TUTULUYOR olmalı.

    Bir önceki test "hiçbir kullanıcı puanının üstünde varlık tutmuyor" der
    ve süzgeç kaldırılsa bile bir üst kademe hiç seçilmediğinde YİNE GEÇER.
    Nitekim öyle oldu: süzgeç doğru çalışıyordu ama seçim aday havuzunda
    düzgün dağılımlıydı ve üst kademeler havuzda azınlıkta (hisse sınıfında
    101 yerliye karşı 21 ABD hissesi ve TEK serbest fon). Ölçülen: 6-7 puanlı
    13 kullanıcının yalnızca 5'i yabancı varlık tutuyordu, `BHE`'yi ise
    HİÇ KİMSE tutmuyordu.

    Sonucu demoda 5, 6 ve 7 puanlı portföylerin ayırt edilememesiydi — yani
    merdivenin tepesi görünmüyordu. Bu test o durumu kilitliyor.
    """
    from app.services.advice_eligibility import asset_risk_level

    generate_dummy_main()

    with Session(engine) as session:
        users = session.execute(select(User)).scalars().all()

        def tepe_seviye(user) -> int:
            return max(
                (
                    asset_risk_level(h.asset.symbol, h.asset.asset_class)
                    for h in user.portfolio.holdings
                    if h.quantity > 0
                ),
                default=0,
            )

        for beklenen_tepe in (6, 7):
            eslesen = [u for u in users if u.risk_survey_score == beklenen_tepe]
            assert eslesen, f"seed'de {beklenen_tepe} puanlı kullanıcı yok"
            eksik = [u.email for u in eslesen if tepe_seviye(u) < beklenen_tepe]
            assert not eksik, (
                f"{beklenen_tepe} puanlı olup {beklenen_tepe}. kademeden hiç varlık "
                f"tutmayan kullanıcılar: {eksik}"
            )


def test_serbest_fon_demoda_en_az_bir_portfoyde(engine):
    """`BHE` evrendeki tek seviye-7 varlık; hiç tutulmazsa 7. kademeyi
    doldurmak için yapılan işin demoda karşılığı olmaz."""
    generate_dummy_main()

    with Session(engine) as session:
        users = session.execute(select(User)).scalars().all()
        tutan = [
            u.email
            for u in users
            if any(h.asset.symbol == "BHE" and h.quantity > 0 for h in u.portfolio.holdings)
        ]
        assert tutan, "hiçbir demo kullanıcısı serbest fon (BHE) tutmuyor"
