"""Giriş akışı ve veri izolasyonu testleri (FR-0, AK 5.4).

Vurgu dört noktada:

1. Giriş gerçekten doğruluyor mu — yanlış şifre geçmemeli, doğru şifre token
   üretmeli ve o token uçlarda çalışmalı.
2. Hatalı kimlik ile hatalı şifre AYNI cevabı vermeli. Ayrıştırılırsa hangi
   T.C. kimlik numaralarının kayıtlı olduğu tek tek denenerek çıkarılabilir.
3. Süresi dolmuş / bozuk / başkasının anahtarıyla imzalanmış token geçmemeli.
4. Kimlik bilgisi atanmamış kullanıcı (national_id / password_hash NULL) hiçbir
   şifreyle giriş yapamamalı — bu sütunlar bilerek nullable (bkz. models/user.py).
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import hash_password
from app.main import app
from app.models import User

_SIFRE = "460213"
_TCKN = "20433218148"


@pytest.fixture()
def giris_kullanicisi(db_session):
    user = User(
        email="giris@example.com",
        full_name="Giris Kullanicisi",
        national_id=_TCKN,
        password_hash=hash_password(_SIFRE),
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def anonim():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Giriş
# ---------------------------------------------------------------------------


def test_login_with_correct_credentials_returns_token_and_user(anonim, giris_kullanicisi):
    response = anonim.post("/api/auth/login", json={"national_id": _TCKN, "password": _SIFRE})
    assert response.status_code == 200

    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    # Süre sunucudan gelir; istemci kendi hesabını yapmasın.
    assert body["expires_in"] == settings.jwt_expire_minutes * 60
    assert body["user"]["id"] == str(giris_kullanicisi.id)
    assert body["user"]["full_name"] == giris_kullanicisi.full_name
    # Kişisel veri en aza indirilmiş: e-posta ve T.C. kimlik numarası dönmez.
    assert "email" not in body["user"]
    assert "national_id" not in body["user"]


def test_login_updates_last_login_at(anonim, db_session, giris_kullanicisi):
    assert giris_kullanicisi.last_login_at is None

    anonim.post("/api/auth/login", json={"national_id": _TCKN, "password": _SIFRE})

    db_session.expire_all()
    guncel = db_session.get(User, giris_kullanicisi.id)
    assert guncel.last_login_at is not None


def test_login_with_wrong_password_returns_401(anonim, giris_kullanicisi):
    response = anonim.post("/api/auth/login", json={"national_id": _TCKN, "password": "000000"})
    assert response.status_code == 401


def test_login_error_does_not_reveal_whether_identity_exists(anonim, giris_kullanicisi):
    """Kayıtlı kimlik + yanlış şifre ile hiç kayıtlı olmayan kimlik AYNI
    cevabı vermeli; aksi halde hangi numaraların sistemde olduğu denenerek
    çıkarılabilir."""
    kayitli_ama_yanlis_sifre = anonim.post(
        "/api/auth/login", json={"national_id": _TCKN, "password": "000000"}
    )
    hic_kayitli_degil = anonim.post(
        "/api/auth/login", json={"national_id": "70013389034", "password": _SIFRE}
    )

    assert kayitli_ama_yanlis_sifre.status_code == hic_kayitli_degil.status_code == 401
    assert kayitli_ama_yanlis_sifre.json() == hic_kayitli_degil.json()


def test_login_rejects_malformed_national_id_with_422(anonim):
    """11 haneden kısa/uzun numara sunucu tarafında da reddedilir; arayüz
    doğrulaması atlatılabilir, asıl kapı burasıdır."""
    response = anonim.post("/api/auth/login", json={"national_id": "123", "password": _SIFRE})
    assert response.status_code == 422


def test_user_without_credentials_cannot_log_in(anonim, db_session):
    """national_id / password_hash NULL olan kullanıcı giriş yapamaz.

    Bu sütunlar mevcut satırların üzerine eklendiği için nullable; NULL
    "kimlik bilgisi atanmamış" demektir ve hiçbir şifreyle eşleşmemelidir.
    """
    user = User(email="kimliksiz@example.com", full_name="Kimliksiz")
    db_session.add(user)
    db_session.commit()

    response = anonim.post(
        "/api/auth/login", json={"national_id": "11111111111", "password": _SIFRE}
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Token doğrulama
# ---------------------------------------------------------------------------


def test_me_returns_the_token_owner(anonim, client_for, giris_kullanicisi):
    response = client_for(giris_kullanicisi).get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["id"] == str(giris_kullanicisi.id)


def test_me_without_token_returns_401(anonim):
    response = anonim.get("/api/auth/me")
    assert response.status_code == 401
    # RFC 6750: 401 yanıtı istemciye hangi şemayı kullanacağını söylemeli.
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_expired_token_returns_401(anonim, giris_kullanicisi):
    suresi_dolmus = jwt.encode(
        {
            "sub": str(giris_kullanicisi.id),
            "iat": datetime.now(UTC) - timedelta(hours=10),
            "exp": datetime.now(UTC) - timedelta(hours=1),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    response = anonim.get("/api/auth/me", headers={"Authorization": f"Bearer {suresi_dolmus}"})
    assert response.status_code == 401


def test_token_signed_with_another_key_returns_401(anonim, giris_kullanicisi):
    """İmza doğrulanmazsa herkes kendi token'ını üretebilirdi."""
    sahte = jwt.encode(
        {
            "sub": str(giris_kullanicisi.id),
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(hours=1),
        },
        "baska-bir-anahtar",
        algorithm=settings.jwt_algorithm,
    )
    response = anonim.get("/api/auth/me", headers={"Authorization": f"Bearer {sahte}"})
    assert response.status_code == 401


def test_unsigned_token_is_rejected(anonim, giris_kullanicisi):
    """`alg: none` ile imzasız token kabul edilmemeli — decode çağrısında
    algoritma listesi tek değerle sınırlandığı için geçmemeli."""
    imzasiz = jwt.encode(
        {
            "sub": str(giris_kullanicisi.id),
            "exp": datetime.now(UTC) + timedelta(hours=1),
        },
        key="",
        algorithm="none",
    )
    response = anonim.get("/api/auth/me", headers={"Authorization": f"Bearer {imzasiz}"})
    assert response.status_code == 401


def test_token_of_deleted_user_returns_401(anonim, db_session, client_for, giris_kullanicisi):
    """Kullanıcı silinirse token imza olarak geçerli kalır ama sahibi yoktur.

    Bu bir yetki değil kimlik sorunudur: 401 üretilir ki istemci yeniden
    giriş yapsın, 403 alıp "yetkim yok" sanmasın.
    """
    client = client_for(giris_kullanicisi)
    db_session.delete(giris_kullanicisi)
    db_session.commit()

    response = client.get("/api/auth/me")
    assert response.status_code == 401
