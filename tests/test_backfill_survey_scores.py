"""Eksik anket puanlarını dolduran betiğin testleri.

Betik, anket özelliğinden ÖNCE seed edilmiş ortamlar için var: orada
`risk_survey_score` boş kalıyor ve demo kullanıcılarının hepsi ilk girişte
kapatılamaz anket ekranına takılıyor.

Vurgu üç noktada:

1. Yazılan puan UYDURULMUYOR — `make seed` o kullanıcıya ne yazacak idiyse
   aynısı yazılıyor.
2. Seed DIŞI kullanıcıya dokunulmuyor: onun boş puanı bir eksiklik değil,
   "anketi henüz doldurmadı" demek.
3. Veri silinmiyor; betik yeniden çalıştırılabilir.
"""

import sys
import uuid

import pytest
from sqlalchemy import select

from app.core.config import RiskProfile, risk_profile_for_survey_score
from app.models import User
from data.seed_ledger import USER_UUID_NAMESPACE, _survey_score
from scripts.backfill_survey_scores import main


def _seed_kullanicisi(db_session, sira: int, profil: RiskProfile) -> User:
    """Seed'in üreteceği KİMLİKLE bir kullanıcı — betik sırayı bundan çözüyor."""
    user = User(
        id=uuid.uuid5(USER_UUID_NAMESPACE, f"user-{sira}"),
        email=f"seed{sira}@example.com",
        full_name=f"Seed Kullanici {sira}",
        risk_profile=profil,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def calistir(monkeypatch):
    def _kos(*args: str):
        monkeypatch.setattr(sys, "argv", ["backfill_survey_scores", *args])
        main()

    return _kos


def test_puan_seedin_yazacagi_degerin_AYNISI(db_session, calistir):
    """Betik kendi kuralını icat etmiyor, seed'in kuralını çağırıyor."""
    user = _seed_kullanicisi(db_session, 0, RiskProfile.CONSERVATIVE)

    calistir()

    db_session.expire_all()
    guncel = db_session.execute(select(User).where(User.id == user.id)).scalar_one()
    assert guncel.risk_survey_score == _survey_score(0, RiskProfile.CONSERVATIVE)


def test_profil_yazilan_puandan_turetilir(db_session, calistir):
    """Puan ile profil ayrışırsa risk motoru yanlış tabloyu kullanır."""
    user = _seed_kullanicisi(db_session, 4, RiskProfile.AGGRESSIVE)

    calistir()

    db_session.expire_all()
    guncel = db_session.execute(select(User).where(User.id == user.id)).scalar_one()
    assert guncel.risk_profile is risk_profile_for_survey_score(guncel.risk_survey_score)


def test_seed_disi_kullaniciya_DOKUNULMAZ(db_session, calistir):
    """ "Üye ol" ile açılmış hesabın boş puanı anlamlıdır: anket doldurulmadı.

    Puan yazmak, alınmamış bir uygunluk beyanını alınmış gibi göstermek olur
    ve kullanıcı anket ekranını hiç görmez.
    """
    yeni = User(
        id=uuid.uuid4(),
        email="uye-ol@example.com",
        full_name="Yeni Uye",
        risk_profile=RiskProfile.BALANCED,
    )
    db_session.add(yeni)
    db_session.commit()

    calistir()

    db_session.expire_all()
    guncel = db_session.execute(select(User).where(User.id == yeni.id)).scalar_one()
    assert guncel.risk_survey_score is None


def test_dry_run_hicbir_sey_yazmaz(db_session, calistir):
    user = _seed_kullanicisi(db_session, 8, RiskProfile.BALANCED)

    calistir("--dry-run")

    db_session.expire_all()
    guncel = db_session.execute(select(User).where(User.id == user.id)).scalar_one()
    assert guncel.risk_survey_score is None


def test_ikinci_kosu_mevcut_puani_DEGISTIRMEZ(db_session, calistir):
    """Yeniden çalıştırılabilirlik: anketi gerçekten doldurmuş bir kullanıcının
    puanı, betik tekrar koştuğunda seed değeriyle EZİLMEMELİ."""
    user = _seed_kullanicisi(db_session, 12, RiskProfile.CONSERVATIVE)
    user.risk_survey_score = 7
    user.risk_profile = risk_profile_for_survey_score(7)
    db_session.commit()

    calistir()

    db_session.expire_all()
    guncel = db_session.execute(select(User).where(User.id == user.id)).scalar_one()
    assert guncel.risk_survey_score == 7
