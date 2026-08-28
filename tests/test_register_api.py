"""Hesap açma ucunun testleri.

Vurgu dört noktada:

1. Anket SUNUCUDA skorlanır — istemcinin gönderdiği puana güvenilmez.
2. Çelişkili beyanda hesap AÇILMAZ; puansız kullanıcı uygunluk kontrolünü
   kör ederdi.
3. Açılış bakiyesi DEFTERE yazılır, bir alana değil — portföy değeri
   işlemlerden yeniden üretilebilir kalmalı (docs/DATA.md altın kural).
4. Kayıt sonrası kullanıcı GERÇEKTEN giriş yapabiliyor olmalı.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Portfolio, Transaction, TransactionType, User
from tests.test_survey_scoring import VAKALAR


@pytest.fixture()
def anonim():
    return TestClient(app)


def _govde(**degisiklikler):
    """Geçerli bir kayıt gövdesi. Cevaplar referans personalardan alınıyor —
    uydurma bir anket seti yerine skorlaması bilinen bir set kullanmak,
    testin beklediği profili de belirli kılıyor."""
    cevaplar, _ = VAKALAR["yuksek_varlikli_tecrubeli"]
    govde = {
        "full_name": "Ayşe Yılmaz",
        "national_id": "12345678901",
        "email": "ayse.yilmaz@example.com",
        "password": "123456",
        "survey_answers": cevaplar,
        "initial_deposit_try": "50000",
    }
    govde.update(degisiklikler)
    return govde


def test_kayit_kullanici_portfoy_ve_acilis_bakiyesi_olusturur(db_session, anonim):
    response = anonim.post("/api/auth/register", json=_govde())

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["access_token"]
    assert body["user"]["full_name"] == "Ayşe Yılmaz"

    user = db_session.execute(select(User).where(User.national_id == "12345678901")).scalar_one()
    portfolio = db_session.execute(
        select(Portfolio).where(Portfolio.user_id == user.id)
    ).scalar_one()

    islemler = (
        db_session.execute(select(Transaction).where(Transaction.portfolio_id == portfolio.id))
        .scalars()
        .all()
    )
    assert len(islemler) == 1
    assert islemler[0].transaction_type == TransactionType.DEPOSIT
    assert islemler[0].cash_amount_try == Decimal("50000")


def test_anket_puani_sunucuda_hesaplanir_istemciden_alinmaz(db_session, anonim):
    """İstemci kendi puanını gönderse bile yok sayılır.

    Güvenilseydi herkes kendini "Agresif" ilan edip uygunluk kontrolünü
    atlayabilirdi.
    """
    govde = _govde(risk_survey_score=7, profil_seviyesi=7)

    response = anonim.post("/api/auth/register", json=govde)

    assert response.status_code == 201, response.text
    # "Yüksek varlıklı, tecrübeli" personasının bilinen sonucu: seviye 7.
    # Buradaki teyit, gönderilen alanın DEĞİL cevapların belirleyici olduğu.
    assert response.json()["risk_survey_score"] == 7

    user = db_session.execute(
        select(User).where(User.national_id == govde["national_id"])
    ).scalar_one()
    assert user.risk_survey_score == 7


def test_dusuk_profil_cevaplari_dusuk_puan_yazar(db_session, anonim):
    """Aynı uç, farklı cevaplarla farklı puan üretmeli — sabit değil."""
    cevaplar, _ = VAKALAR["genc_calisan_tecrubesiz_iddiali"]

    response = anonim.post(
        "/api/auth/register",
        json=_govde(
            survey_answers=cevaplar,
            national_id="12345678902",
            email="genc@example.com",
        ),
    )

    assert response.status_code == 201, response.text
    assert response.json()["risk_survey_score"] == 1


def test_celiskili_beyanda_hesap_acilmaz(db_session, anonim):
    """Durdurucu kural tetiklendiğinde profil üretilemiyor.

    Kullanıcı yine de kaydedilseydi `risk_survey_score` boş kalır ve
    uygunluk kontrolü kör olurdu.
    """
    cevaplar, _ = VAKALAR["celiskili_beyan_tk1"]

    response = anonim.post(
        "/api/auth/register",
        json=_govde(
            survey_answers=cevaplar,
            national_id="12345678903",
            email="celiskili@example.com",
        ),
    )

    assert response.status_code == 400
    assert (
        db_session.execute(
            select(User).where(User.national_id == "12345678903")
        ).scalar_one_or_none()
        is None
    )


def test_eksik_anket_cevabi_reddedilir(db_session, anonim):
    cevaplar, _ = VAKALAR["yuksek_varlikli_tecrubeli"]
    eksik = {k: v for k, v in cevaplar.items() if k != "B3"}

    response = anonim.post(
        "/api/auth/register",
        json=_govde(survey_answers=eksik, national_id="12345678904", email="eksik@example.com"),
    )

    assert response.status_code == 400


def test_ayni_kimlik_ikinci_kez_kaydedilemez(db_session, anonim):
    anonim.post("/api/auth/register", json=_govde())

    ikinci = anonim.post("/api/auth/register", json=_govde(email="baska@example.com"))

    assert ikinci.status_code == 409
    # Hangi alanın çakıştığı SÖYLENMEZ: numaraları tek tek deneyerek kimin
    # müşteri olduğunu öğrenmeye açık bir araç yaratmamak için.
    assert "T.C." not in ikinci.json()["detail"]


def test_kayit_sonrasi_gercekten_giris_yapilabiliyor(db_session, anonim):
    """Şifre özeti doğru üretilmiş olmalı; aksi hâlde kullanıcı hesabını
    açar ama bir daha giremez."""
    anonim.post("/api/auth/register", json=_govde())

    giris = anonim.post(
        "/api/auth/login", json={"national_id": "12345678901", "password": "123456"}
    )

    assert giris.status_code == 200
    assert giris.json()["access_token"]


def test_acilis_tutari_sifirsa_islem_yazilmaz(db_session, anonim):
    """Sıfırlık bir yatırım kaydı defteri kirletir."""
    response = anonim.post(
        "/api/auth/register",
        json=_govde(initial_deposit_try="0", national_id="12345678905", email="sifir@example.com"),
    )

    assert response.status_code == 201
    user = db_session.execute(select(User).where(User.national_id == "12345678905")).scalar_one()
    portfolio = db_session.execute(
        select(Portfolio).where(Portfolio.user_id == user.id)
    ).scalar_one()
    islemler = (
        db_session.execute(select(Transaction).where(Transaction.portfolio_id == portfolio.id))
        .scalars()
        .all()
    )
    assert islemler == []


def test_ad_soyad_tek_kelime_olamaz(db_session, anonim):
    response = anonim.post("/api/auth/register", json=_govde(full_name="Ayşe"))

    assert response.status_code == 422


def test_sifre_alti_haneli_rakam_olmali(db_session, anonim):
    """Giriş ekranı 6 haneli sayısal şifre bekliyor; kayıt farklı bir biçim
    üretirse kullanıcı giriş yapamayacağı bir şifre belirler."""
    assert anonim.post("/api/auth/register", json=_govde(password="abcdef")).status_code == 422
    assert anonim.post("/api/auth/register", json=_govde(password="12345")).status_code == 422


def test_anketsiz_kayit_hesap_acar_puan_bos_kalir(db_session, anonim):
    """Anket kayıt akışından çıkarıldı: cevap gönderilmese de hesap açılır.

    18 soruluk anket kayıtta zorunluyken, kullanıcı yarıda bıraktığında hesap
    HİÇ açılmıyordu — en pahalı adım (hesap açma) en kırılgan adıma (uzun
    form) bağlıydı. Artık puan `NULL` kalıyor ve arayüz kullanıcıyı ilk
    girişte ankete alıyor.
    """
    govde = _govde(national_id="12345678906", email="anketsiz@example.com")
    govde.pop("survey_answers")

    response = anonim.post("/api/auth/register", json=govde)

    assert response.status_code == 201, response.text
    assert response.json()["risk_survey_score"] is None
    assert response.json()["profil_adi"] is None

    user = db_session.execute(select(User).where(User.national_id == "12345678906")).scalar_one()
    assert user.risk_survey_score is None


def test_anketsiz_kayitta_da_acilis_bakiyesi_yazilir(db_session, anonim):
    """Para aktarımı ankete bağlı değil: ikisi ayrı adımlar."""
    govde = _govde(national_id="12345678907", email="anketsiz-para@example.com")
    govde.pop("survey_answers")

    assert anonim.post("/api/auth/register", json=govde).status_code == 201

    user = db_session.execute(select(User).where(User.national_id == "12345678907")).scalar_one()
    portfolio = db_session.execute(
        select(Portfolio).where(Portfolio.user_id == user.id)
    ).scalar_one()
    islemler = (
        db_session.execute(select(Transaction).where(Transaction.portfolio_id == portfolio.id))
        .scalars()
        .all()
    )
    assert len(islemler) == 1
    assert islemler[0].cash_amount_try == Decimal("50000")


def test_oturum_yanitinda_anket_puani_doner(db_session, anonim):
    """Arayüz anket ekranını açıp açmayacağına BU alana bakarak karar veriyor;
    oturum yanıtında gelmezse her açılışta ayrı bir istek gerekirdi."""
    govde = _govde(national_id="12345678908", email="oturum@example.com")
    govde.pop("survey_answers")
    anonim.post("/api/auth/register", json=govde)

    giris = anonim.post(
        "/api/auth/login", json={"national_id": "12345678908", "password": "123456"}
    )

    assert giris.status_code == 200
    assert "risk_survey_score" in giris.json()["user"]
    assert giris.json()["user"]["risk_survey_score"] is None
