"""Risk değerlendirmesi ucunun testleri.

Vurgu üç noktada:

1. Uç, `risk_service`'in çıktısını OLDUĞU GİBİ taşımalı — kendi hesabını
   yapmamalı, alan kırpmamalı. Sayısal değerlerin hiçbiri burada üretilmez.
2. Veri izolasyonu (AK 5.4): başkasının riski okunamaz.
3. Yeterli veri yoksa `null` dönmeli, tahmini bir değerle DOLDURULMAMALI
   (AK 2.7 / 5.5) — bu, ekranda "0" gösterip "riskin yok" izlenimi vermeyi
   engelleyen kural.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.config import AssetClass, RiskProfile
from app.main import app
from app.models import Asset, Portfolio, PriceHistory, TransactionType, User
from app.services.ledger_service import rebuild_holdings, record_transaction


@pytest.fixture()
def anonim():
    return TestClient(app)


def _portfoy_kur(db_session, email: str, gun_sayisi: int) -> User:
    """`gun_sayisi` kadar günlük fiyatı olan tek hisselik bir portföy kurar."""
    user = User(email=email, full_name="Risk Kullanicisi", risk_profile=RiskProfile.BALANCED)
    stock = Asset(symbol="TRS", name="Test Hisse", asset_class=AssetClass.STOCK, currency="TRY")
    db_session.add_all([user, stock])
    db_session.flush()
    portfolio = Portfolio(user_id=user.id)
    db_session.add(portfolio)
    db_session.flush()

    baslangic = date(2026, 1, 1)
    fiyat = 100
    for i in range(gun_sayisi):
        # Küçük bir salınım: volatilite sıfır çıkmasın.
        db_session.add(
            PriceHistory(
                asset_id=stock.id,
                price_date=baslangic + timedelta(days=i),
                close_price=Decimal(fiyat + (i % 5)),
            )
        )
    record_transaction(
        db_session,
        portfolio.id,
        TransactionType.DEPOSIT,
        transaction_date=datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
        cash_amount_try=Decimal(10_000),
    )
    record_transaction(
        db_session,
        portfolio.id,
        TransactionType.BUY,
        transaction_date=datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
        asset_id=stock.id,
        quantity=Decimal(100),
        price=Decimal(100),
    )
    rebuild_holdings(db_session, portfolio.id)
    db_session.commit()
    return user


def test_returns_assessment_for_own_portfolio(db_session, client_for):
    user = _portfoy_kur(db_session, "risk-ok@example.com", gun_sayisi=200)

    response = client_for(user).get(f"/api/risk/{user.id}")
    assert response.status_code == 200

    body = response.json()
    assert body["user_id"] == str(user.id)
    assert body["risk_profile"] == RiskProfile.BALANCED.value
    # Sunum katmanının ihtiyaç duyduğu alanlar sözleşmede olmalı.
    for alan in ("risk_level", "is_within_profile", "metrics", "warnings", "disclaimer"):
        assert alan in body, alan
    for alan in ("annualized_volatility_percent", "value_at_risk_try", "sharpe_ratio"):
        assert alan in body["metrics"], alan


def test_disclaimer_is_always_present(db_session, client_for):
    """CLAUDE.md §4: her finansal çıktı sorumluluk reddi taşımak zorunda."""
    user = _portfoy_kur(db_session, "risk-uyari@example.com", gun_sayisi=200)

    body = client_for(user).get(f"/api/risk/{user.id}").json()
    assert "yatırım tavsiyesi değildir" in body["disclaimer"].lower()


def test_insufficient_history_returns_null_not_zero(db_session, client_for):
    """Yetersiz fiyat geçmişinde volatilite `null` dönmeli.

    `0` dönseydi arayüz "riskiniz sıfır" gösterirdi — elimizde olmayan bir
    bilgiyi uydurmak olurdu (AK 2.7 / 5.5). Sebep `warnings`'te yazmalı ki
    kullanıcı neden hesaplanamadığını görebilsin.
    """
    user = _portfoy_kur(db_session, "risk-kisa@example.com", gun_sayisi=3)

    body = client_for(user).get(f"/api/risk/{user.id}").json()

    assert body["risk_level"] is None
    assert body["metrics"]["annualized_volatility_percent"] is None
    assert body["warnings"], "hesaplanamama sebebi kullanıcıya bildirilmeli"


def test_ak_5_4_another_users_risk_is_forbidden(db_session, client_for):
    """Başkasının risk değerlendirmesi okunamaz."""
    sahip = _portfoy_kur(db_session, "risk-sahip@example.com", gun_sayisi=200)

    response = client_for(sahip).get(f"/api/risk/{uuid.uuid4()}")
    assert response.status_code == 403


def test_request_without_token_is_unauthorized(db_session, client_for):
    user = _portfoy_kur(db_session, "risk-tokensiz@example.com", gun_sayisi=200)

    response = client_for().get(f"/api/risk/{user.id}")
    assert response.status_code == 401


def test_profile_override_does_not_change_stored_profile(db_session, client_for):
    """ "Ya agresif olsaydım?" senaryosu kalıcı profili DEĞİŞTİRMEMELİ.

    Değiştirseydi, bir bakış açısını denemek kullanıcının beyan ettiği risk
    toleransını sessizce ezerdi.
    """
    user = _portfoy_kur(db_session, "risk-override@example.com", gun_sayisi=200)

    body = (
        client_for(user)
        .get(f"/api/risk/{user.id}", params={"profile_override": RiskProfile.AGGRESSIVE.value})
        .json()
    )
    assert body["risk_profile"] == RiskProfile.AGGRESSIVE.value
    assert body["risk_profile_source"] == "override"

    db_session.expire_all()
    assert db_session.get(User, user.id).risk_profile is RiskProfile.BALANCED


def test_unknown_profile_override_is_rejected(db_session, client_for):
    user = _portfoy_kur(db_session, "risk-gecersiz@example.com", gun_sayisi=200)

    response = client_for(user).get(
        f"/api/risk/{user.id}", params={"profile_override": "boyle-bir-profil-yok"}
    )
    assert response.status_code == 422
