"""Risk profili okuma/yazma uçlarının testleri (Not 1 / Not 4).

Vurgu üç noktada:
1. Anket sonucu gerçekten KALICI yazılıyor mu (projedeki ilk yazma ucu),
2. Tanınmayan profil değeri 422, bilinmeyen kullanıcı 404 — ikisi farklı şey,
3. Kademe sayısı hiçbir yerde SABİT YAZILMAMIŞ olmalı: testler de dahil.
   Profil 4'ten 7'ye çıktığında bu dosyanın değişmesi gerekmiyor; bu yüzden
   beklenen değerler `RiskProfile` enum'ından türetiliyor, "conservative"
   gibi sabitler elle yazılmıyor.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import RiskProfile
from app.main import app
from app.models import User


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def profil_kullanicisi(db_session):
    user = User(email="anket@example.com", full_name="Anket Kullanicisi")
    db_session.add(user)
    db_session.commit()
    return user


def _baska_profil(mevcut: RiskProfile) -> RiskProfile:
    """Mevcut olandan farklı, geçerli bir profil seçer. Enum'dan türetiliyor
    ki kademe sayısı değiştiğinde test kendiliğinden uyum sağlasın."""
    return next(p for p in RiskProfile if p is not mevcut)


def test_read_risk_profile_returns_current_and_options(client, profil_kullanicisi):
    response = client.get(f"/api/users/{profil_kullanicisi.id}/risk-profile")
    assert response.status_code == 200

    body = response.json()
    assert body["user_id"] == str(profil_kullanicisi.id)
    assert body["risk_profile"] == profil_kullanicisi.risk_profile.value
    # Arayüz seçenekleri kendi tarafında sabit yazmasın diye dönüyor;
    # enum'daki her kademe listede olmalı.
    assert body["available_profiles"] == [p.value for p in RiskProfile]


def test_update_risk_profile_persists_survey_result(client, db_session, profil_kullanicisi):
    """Anket sonucu veritabanına gerçekten yazılmalı — yanıtın doğru olması
    yetmez, ikinci bir okuma da yeni değeri görmeli."""
    hedef = _baska_profil(profil_kullanicisi.risk_profile)

    response = client.put(
        f"/api/users/{profil_kullanicisi.id}/risk-profile",
        json={"risk_profile": hedef.value},
    )
    assert response.status_code == 200
    assert response.json()["risk_profile"] == hedef.value

    # Uç kendi oturumunda commit ettiği için test oturumunun kimlik haritası
    # bayat kalır; tazelemeden okumak eski değeri gösterirdi.
    db_session.expire_all()
    assert db_session.get(User, profil_kullanicisi.id).risk_profile is hedef

    tekrar_okuma = client.get(f"/api/users/{profil_kullanicisi.id}/risk-profile")
    assert tekrar_okuma.json()["risk_profile"] == hedef.value


def test_update_risk_profile_is_idempotent(client, profil_kullanicisi):
    """Anket ekranı aynı sonucu tekrar gönderebilir; bu hata değildir."""
    hedef = _baska_profil(profil_kullanicisi.risk_profile)
    yol = f"/api/users/{profil_kullanicisi.id}/risk-profile"

    ilk = client.put(yol, json={"risk_profile": hedef.value})
    ikinci = client.put(yol, json={"risk_profile": hedef.value})

    assert ilk.status_code == 200
    assert ikinci.status_code == 200
    assert ikinci.json()["risk_profile"] == hedef.value


def test_every_defined_profile_is_accepted(client, profil_kullanicisi):
    """Enum'da tanımlı HER kademe yazılabilmeli.

    Regresyon koruması: kademe sayısı 4'ten 7'ye çıkarıldığında yalnızca
    enum ve veritabanı enum'ı güncellenip uç/servis unutulursa, yeni
    kademeler sessizce reddedilir ve anket sonucu kaydedilemez. Bu test o
    durumu yakalar ve yeni kademe eklendiğinde kendiliğinden onu da dener.
    """
    yol = f"/api/users/{profil_kullanicisi.id}/risk-profile"
    for profil in RiskProfile:
        response = client.put(yol, json={"risk_profile": profil.value})
        assert response.status_code == 200, profil.value
        assert response.json()["risk_profile"] == profil.value


def test_unknown_profile_value_returns_422(client, profil_kullanicisi):
    response = client.put(
        f"/api/users/{profil_kullanicisi.id}/risk-profile",
        json={"risk_profile": "boyle-bir-profil-yok"},
    )
    assert response.status_code == 422


def test_missing_body_field_returns_422(client, profil_kullanicisi):
    response = client.put(f"/api/users/{profil_kullanicisi.id}/risk-profile", json={})
    assert response.status_code == 422


def test_unknown_user_returns_404_on_read_and_write(client, db_session):
    """Kullanıcı yoksa 404 — "veri yetersiz" (409) ile karıştırılmamalı."""
    eksik = uuid.uuid4()

    okuma = client.get(f"/api/users/{eksik}/risk-profile")
    assert okuma.status_code == 404

    yazma = client.put(
        f"/api/users/{eksik}/risk-profile",
        json={"risk_profile": next(iter(RiskProfile)).value},
    )
    assert yazma.status_code == 404


def test_profile_write_does_not_touch_other_fields(client, db_session, profil_kullanicisi):
    """Yazma kapısı dar: yalnızca risk_profile değişir.

    Gövdeye başka alanlar konsa bile (arayüz fazladan alan gönderirse ya da
    kötü niyetli bir istek gelirse) e-posta/ad değişmemeli.
    """
    eski_email = profil_kullanicisi.email
    eski_ad = profil_kullanicisi.full_name
    hedef = _baska_profil(profil_kullanicisi.risk_profile)

    response = client.put(
        f"/api/users/{profil_kullanicisi.id}/risk-profile",
        json={"risk_profile": hedef.value, "email": "saldirgan@example.com", "full_name": "Yeni"},
    )
    assert response.status_code == 200

    db_session.expire_all()
    guncel = db_session.get(User, profil_kullanicisi.id)
    assert guncel.email == eski_email
    assert guncel.full_name == eski_ad
    assert guncel.risk_profile is hedef
