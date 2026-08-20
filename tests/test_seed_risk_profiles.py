"""Seed'in risk profili / portföy arketipi dağıtımı.

Bağlam: `growth` (Büyüme) profili b26e8dab6ef9 ile enum'a eklendi ve
risk_service'in senaryo motoru onun için ayrı sabitler tanımlıyor, ama seed
yalnızca üç profil üretiyordu — yani veritabanında tek bir Büyüme kullanıcısı
yoktu ve o kod yolu hiç çalışmıyordu. Buradaki testler o durumun geri
gelmesini engeller.

DB gerektirmez: dağıtım saf bir fonksiyon (`_profile_and_archetype`).
"""

from collections import Counter

from app.core.config import RiskProfile
from data.seed_ledger import (
    NUM_USERS,
    PORTFOLIO_ARCHETYPE_CYCLE,
    RISK_PROFILE_CYCLE,
    _profile_and_archetype,
)


def _all_pairs():
    return [_profile_and_archetype(i) for i in range(NUM_USERS)]


def test_seed_dort_risk_profilinin_hepsini_uretir():
    """RiskProfile'daki her değer için en az bir kullanıcı üretilmeli —
    aksi halde o profilin risk hesabı, senaryo üretimi ve arayüz gösterimi
    demoda hiç test edilemez."""
    uretilen = {profile for profile, _ in _all_pairs()}

    assert uretilen == set(RiskProfile), f"uretilmeyen profil(ler): {set(RiskProfile) - uretilen}"
    assert RiskProfile.GROWTH in uretilen


def test_ak_2_6_her_profil_arketip_bilesimi_ornek_uretir():
    """AK-2.6 'farklı yapılar farklı sonuç üretebilmeli': her risk profili
    her portföy yapısıyla en az bir kez eşleşmeli.

    Bu testin asıl koruduğu şey ince: profil ve arketip AYNI sayaçla (
    `user_index % len(...)`) dağıtılırsa üretilen bileşim sayısı iki
    uzunluğun en küçük ortak katıyla sınırlanır. İkisi de 4 uzunlukta
    olduğundan bu 16 değil 4 demektir — her profil tek bir arketiple
    görülür ve risk motoru ayrıştırılamaz hale gelir.
    """
    beklenen_bilesim_sayisi = len(RISK_PROFILE_CYCLE) * len(PORTFOLIO_ARCHETYPE_CYCLE)
    sayim = Counter(_all_pairs())

    assert len(sayim) == beklenen_bilesim_sayisi
    assert min(sayim.values()) >= 2, f"tek örnekli bileşim var: {sayim}"


def test_seed_profil_dagitimi_dengeli():
    """Hiçbir profil diğerlerinin yarısından az örnek almamalı; aksi halde
    o profilin metrikleri istatistiksel olarak anlamsızlaşır."""
    dagilim = Counter(profile for profile, _ in _all_pairs())

    assert min(dagilim.values()) * 2 >= max(dagilim.values()), dagilim
    assert sum(dagilim.values()) == NUM_USERS


def test_seed_profil_dagitimi_deterministik():
    """SEED=42 / ANCHOR_DATE sözleşmesi: dağıtımda rastgelelik yok, aynı
    sıra numarası her zaman aynı çifti verir."""
    assert _all_pairs() == _all_pairs()
