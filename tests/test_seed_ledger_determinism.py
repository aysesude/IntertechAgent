"""Seed'in belirlenimciliği ve arketip × risk profili eşlemesi — Not 5 (PO, 2026-08).

Saf fonksiyon testleri: veritabanı kullanmaz, `db_session` fixture'ına
dokunmaz (o fixture teardown'da tüm tabloları siliyor).

Not: Bu dosya daha önce (AK-2.6) profil ile arketipin BAĞIMSIZ, farklı hızda
dönen sayaçlarla 16 kombinasyonun tamamını (kasıtlı uyumsuzluklar dahil)
ürettiğini doğruluyordu. PO Not 5 ile bu tasarımı geri aldı: dummy veri artık
tutarlı olmalı, her arketip tam olarak bir risk profiline sabit biçimde
eşlenir. Aşağıdaki testler bu yeni sözleşmeyi doğrular.
"""

from app.core.config import RISK_MAX_CATEGORY_WEIGHT, AssetClass, RiskProfile
from data.seed_ledger import (
    ARCHETYPE_RISK_PROFILE,
    PORTFOLIO_ARCHETYPE_CYCLE,
    PORTFOLIO_ARCHETYPES,
    TOPLAM_KULLANICI,
    _user_id,
)


def test_her_arketipin_tam_olarak_bir_risk_profili_var():
    """ÜRÜN SAHİBİ KARARI (Not 5): profil artık arketipten bağımsız değil —
    her arketip tam olarak bir risk profiline, sabit biçimde eşlenir."""
    assert set(ARCHETYPE_RISK_PROFILE) == set(
        PORTFOLIO_ARCHETYPES
    ), "eşleme tüm arketipleri kapsamalı"
    assert set(ARCHETYPE_RISK_PROFILE.values()) == set(
        RiskProfile
    ), "dört profilin (GROWTH dahil) tamamı en az bir arketiple temsil edilmeli"
    # İki arketip aynı profile düşmemeli: aksi halde bir profil hiç
    # üretilmez ya da 50 kullanıcı arasındaki dağılım aşırı dengesizleşir.
    assert len(set(ARCHETYPE_RISK_PROFILE.values())) == len(ARCHETYPE_RISK_PROFILE)


def test_eslesen_profil_arketipin_hisse_agirligini_kaldirabiliyor():
    """Hiçbir arketip, eşlendiği profilin Hisse üst sınırını aşmamalı —
    aksi halde bu eşleme daha üretim anında Not 3'ü ihlal eden veri üretir."""
    for archetype_name, profile in ARCHETYPE_RISK_PROFILE.items():
        stock_weight = PORTFOLIO_ARCHETYPES[archetype_name].get(AssetClass.STOCK, (0.0, 0))[0]
        limit = float(RISK_MAX_CATEGORY_WEIGHT[profile][AssetClass.STOCK])
        assert stock_weight <= limit, (
            f"{archetype_name} (%{stock_weight:.0%} hisse) {profile.value} "
            f"profilinin sınırını (%{limit:.0%}) aşıyor"
        )


def test_arketip_her_kullanicida_bir_ilerler():
    """PORTFOLIO_ARCHETYPE_CYCLE her kullanıcıda bir döner; dört kullanıcıda
    tüm arketipler (dolayısıyla tüm profiller) görülür."""
    ilk_dort = [PORTFOLIO_ARCHETYPE_CYCLE[i % len(PORTFOLIO_ARCHETYPE_CYCLE)] for i in range(4)]
    assert len(set(ilk_dort)) == len(PORTFOLIO_ARCHETYPE_CYCLE)


def test_kullanici_kimlikleri_tohuma_bagli():
    """UUID'ler her seed'de aynı olmalı.

    Model varsayılanı `uuid.uuid4`, SEED'den etkilenmiyordu: isimler ve
    portföyler aynı üretilirken kimlikler her `make seed` sonrası değişiyor,
    elde tutulan test kimlikleri ölüyordu.
    """
    # Demo personası da dahil (TOPLAM_KULLANICI): kimliği aynı ad alanından
    # üretiliyor, çakışma kontrolü onu da kapsamalı.
    ilk = [_user_id(i) for i in range(TOPLAM_KULLANICI)]
    ikinci = [_user_id(i) for i in range(TOPLAM_KULLANICI)]

    assert ilk == ikinci, "aynı sıra farklı UUID üretti"
    assert len(set(ilk)) == TOPLAM_KULLANICI, "UUID çakışması"
    # uuid5 sürüm damgası — yanlışlıkla uuid4'e dönülürse yakalanır.
    assert all(u.version == 5 for u in ilk)
