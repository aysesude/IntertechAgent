"""Seed'in belirlenimciliği ve profil × arketip dağıtımı — AK-2.6.

Saf fonksiyon testleri: veritabanı kullanmaz, `db_session` fixture'ına
dokunmaz (o fixture teardown'da tüm tabloları siliyor).
"""

from collections import Counter

from app.core.config import RiskProfile
from data.seed_ledger import (
    NUM_USERS,
    PORTFOLIO_ARCHETYPE_CYCLE,
    RISK_PROFILE_CYCLE,
    _profile_and_archetype,
    _user_id,
)


def test_ak_2_6_butun_profil_arketip_bilesimleri_uretilir():
    """16 bileşimin tamamı çıkmalı.

    Regresyon: profil ve arketip AYNI sayaçla dönerse üretilen bileşim sayısı
    iki uzunluğun en küçük ortak katıyla sınırlanır. 'growth' eklenmeden önce
    listeler 3 ve 4 uzunluktaydı (aralarında asal, ekok 12 → hepsi çıkıyordu);
    'growth' listeyi 4'e çıkarınca ekok 4 olur ve 16 bileşimden yalnızca 4'ü
    üretilirdi — agresif profil YALNIZCA nakit ağırlıklı portföyle görülürdü.
    """
    bilesimler = {_profile_and_archetype(i) for i in range(NUM_USERS)}
    beklenen = {
        (profile, archetype)
        for profile in RISK_PROFILE_CYCLE
        for archetype in PORTFOLIO_ARCHETYPE_CYCLE
    }
    assert bilesimler == beklenen, f"eksik bileşim: {beklenen - bilesimler}"


def test_dort_profil_de_uretilir_ve_dengeli_dagilir():
    """'growth' dahil dört profil de yeterli sayıda kullanıcıya düşmeli."""
    dagilim = Counter(_profile_and_archetype(i)[0] for i in range(NUM_USERS))

    assert set(dagilim) == set(RiskProfile), "bir profil hiç üretilmiyor"
    # Hiçbir profil tek örnekte kalmasın; risk motoru o yolda test edilemez.
    assert min(dagilim.values()) >= NUM_USERS // len(RiskProfile) - 2


def test_arketip_her_kullanicida_profil_her_dortte_bir_doner():
    """Sayaç hızları farklı olmalı — bileşim çeşitliliği buna bağlı."""
    ilk_dort = [_profile_and_archetype(i) for i in range(4)]
    # Arketip her adımda değişir.
    assert len({a for _, a in ilk_dort}) == 4
    # Profil aynı kalır.
    assert len({p for p, _ in ilk_dort}) == 1
    # Beşinci kullanıcıda profil ilerler, arketip başa döner.
    assert _profile_and_archetype(4)[0] != ilk_dort[0][0]
    assert _profile_and_archetype(4)[1] == ilk_dort[0][1]


def test_kullanici_kimlikleri_tohuma_bagli():
    """UUID'ler her seed'de aynı olmalı.

    Model varsayılanı `uuid.uuid4`, SEED'den etkilenmiyordu: isimler ve
    portföyler aynı üretilirken kimlikler her `make seed` sonrası değişiyor,
    elde tutulan test kimlikleri ölüyordu.
    """
    ilk = [_user_id(i) for i in range(NUM_USERS)]
    ikinci = [_user_id(i) for i in range(NUM_USERS)]

    assert ilk == ikinci, "aynı sıra farklı UUID üretti"
    assert len(set(ilk)) == NUM_USERS, "UUID çakışması"
    # uuid5 sürüm damgası — yanlışlıkla uuid4'e dönülürse yakalanır.
    assert all(u.version == 5 for u in ilk)
