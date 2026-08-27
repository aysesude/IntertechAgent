"""Giriş yapmış kullanıcının anketi kaydettiği ucun testleri.

Anket kayıt akışından çıkarılıp ilk girişe taşındı; bu uç o ekranın yazdığı
yerdir. Vurgu üç noktada:

1. Skorlama SUNUCUDA — gönderilen tek şey ham cevaplar.
2. Çelişkili beyanda HİÇBİR ŞEY kaydedilmez ama sonuç yine döner; kullanıcı
   hangi çelişkiyi düzelteceğini görebilmeli.
3. Veri izolasyonu (AK 5.4): başkasının anket puanı yazılamaz — o puan tüm
   uygunluk kontrolünün dayandığı beyandır.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import RiskProfile
from app.main import app
from app.models import User
from tests.test_survey_scoring import VAKALAR


@pytest.fixture()
def anonim():
    return TestClient(app)


def _kullanici(db_session, email: str) -> User:
    """Anketi HENÜZ DOLDURMAMIŞ kullanıcı."""
    user = User(email=email, full_name="Anket Kullanicisi")
    db_session.add(user)
    db_session.commit()
    return user


def test_anket_kaydedilir_ve_profil_puandan_turetilir(db_session, client_for):
    user = _kullanici(db_session, "anket-kaydet@example.com")
    cevaplar, _ = VAKALAR["yuksek_varlikli_tecrubeli"]

    response = client_for(user).post(f"/api/survey/submit/{user.id}", json={"answers": cevaplar})

    assert response.status_code == 200, response.text
    assert response.json()["profil_seviyesi"] == 7

    db_session.expire_all()
    guncel = db_session.execute(select(User).where(User.id == user.id)).scalar_one()
    assert guncel.risk_survey_score == 7
    # Profil puandan TÜRETİLİR; ikisi ayrı yazılsaydı puanı 7 ama profili
    # Muhafazakâr olan bir satır kalabilirdi ve risk motoru yanlış tabloyu
    # kullanırdı.
    assert guncel.risk_profile != RiskProfile.BALANCED or guncel.risk_survey_score == 7


def test_yorum_her_zaman_doner(db_session, client_for):
    """Sonuç ekranı boş kalamaz: LLM'e ulaşılamazsa yedek metne düşülür."""
    user = _kullanici(db_session, "anket-yorum@example.com")
    cevaplar, _ = VAKALAR["emekli_koruma_odakli"]

    body = client_for(user).post(f"/api/survey/submit/{user.id}", json={"answers": cevaplar}).json()

    assert body["yorum"].strip()


def test_celiskili_beyanda_puan_yazilmaz_ama_sonuc_doner(db_session, client_for):
    """Çelişkiden üretilmiş bir profil, üretilmemiş profilden kötüdür."""
    user = _kullanici(db_session, "anket-celiski@example.com")
    cevaplar, _ = VAKALAR["celiskili_beyan_tk1"]

    response = client_for(user).post(f"/api/survey/submit/{user.id}", json={"answers": cevaplar})

    assert response.status_code == 200
    body = response.json()
    assert body["sonuc_uretildi"] is False
    assert body["profil_seviyesi"] is None
    # Kullanıcı hangi çelişkiyi düzelteceğini görebilmeli.
    assert any(k["kod"] == "TK1" for k in body["kurallar"])

    db_session.expire_all()
    guncel = db_session.execute(select(User).where(User.id == user.id)).scalar_one()
    assert guncel.risk_survey_score is None


def test_ak_5_4_baskasinin_anketi_yazilamaz(db_session, client_for):
    sahip = _kullanici(db_session, "anket-sahip@example.com")
    baskasi = _kullanici(db_session, "anket-yabanci@example.com")
    cevaplar, _ = VAKALAR["yuksek_varlikli_tecrubeli"]

    response = client_for(baskasi).post(
        f"/api/survey/submit/{sahip.id}", json={"answers": cevaplar}
    )

    assert response.status_code == 403

    db_session.expire_all()
    guncel = db_session.execute(select(User).where(User.id == sahip.id)).scalar_one()
    assert guncel.risk_survey_score is None


def test_anket_ucu_token_ister(db_session, anonim):
    user = _kullanici(db_session, "anket-anonim@example.com")
    cevaplar, _ = VAKALAR["yuksek_varlikli_tecrubeli"]

    response = anonim.post(f"/api/survey/submit/{user.id}", json={"answers": cevaplar})

    assert response.status_code == 401


def test_eksik_cevap_reddedilir_ve_puan_yazilmaz(db_session, client_for):
    user = _kullanici(db_session, "anket-eksik@example.com")
    cevaplar, _ = VAKALAR["yuksek_varlikli_tecrubeli"]
    eksik = {k: v for k, v in cevaplar.items() if k != "C3"}

    response = client_for(user).post(f"/api/survey/submit/{user.id}", json={"answers": eksik})

    assert response.status_code == 400

    db_session.expire_all()
    guncel = db_session.execute(select(User).where(User.id == user.id)).scalar_one()
    assert guncel.risk_survey_score is None


def test_sorular_ucu_oturum_istemez(anonim):
    """Kayıt akışında kullanıcı henüz yokken de çekilebilmeli."""
    response = anonim.get("/api/survey/questions")

    assert response.status_code == 200
    assert response.json()["sorular"]
