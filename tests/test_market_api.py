"""Piyasa ekranı uçlarının testleri.

Vurgu üç noktada:

1. Değişim yüzdesi UYDURULMAZ: seride tek nokta varsa `null` döner, `0`
   değil. Sıfır "değişmedi" demektir ve elimizde olmayan bir bilgiyi
   söylemek olurdu (AK 5.5).
2. Değişim, TAKVİM günü değil bir önceki İŞLEM günü ile karşılaştırılır —
   piyasa hafta sonu ve tatilde kapalı.
3. Veri izolasyonu (AK 5.4): başkasının portföy etkisi okunamaz.

`/headlines` burada test EDİLMİYOR: dış bir siteye canlı çıkıyor, testte ağ
kullanmıyoruz. Ayrıştırıcısının kendi testi var (test_bloomberg_ht_provider).
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


def _fiyatli_varlik(db_session, symbol: str, kapanislar: list[tuple[date, int]]) -> Asset:
    asset = Asset(
        symbol=symbol,
        name=f"{symbol} Testi",
        asset_class=AssetClass.STOCK,
        currency="TRY",
    )
    db_session.add(asset)
    db_session.flush()
    for gun, fiyat in kapanislar:
        db_session.add(PriceHistory(asset_id=asset.id, price_date=gun, close_price=Decimal(fiyat)))
    return asset


def _portfoy_kur(db_session, email: str, asset: Asset) -> User:
    user = User(email=email, full_name="Piyasa Kullanicisi", risk_profile=RiskProfile.BALANCED)
    db_session.add(user)
    db_session.flush()
    portfolio = Portfolio(user_id=user.id)
    db_session.add(portfolio)
    db_session.flush()

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
        asset_id=asset.id,
        quantity=Decimal(10),
        price=Decimal(100),
    )
    rebuild_holdings(db_session, portfolio.id)
    db_session.commit()
    return user


def test_ak_5_4_baskasinin_etkisi_okunamaz(db_session, client_for):
    bugun = date.today()
    asset = _fiyatli_varlik(db_session, "PZR", [(bugun - timedelta(days=1), 100), (bugun, 110)])
    sahip = _portfoy_kur(db_session, "piyasa-sahip@example.com", asset)
    baskasi = User(email="piyasa-yabanci@example.com", full_name="Yabanci")
    db_session.add(baskasi)
    db_session.commit()

    response = client_for(baskasi).get(f"/api/market/influence/{sahip.id}")

    assert response.status_code == 403


def test_etki_ucu_token_ister(db_session, anonim):
    response = anonim.get(f"/api/market/influence/{uuid.uuid4()}")

    assert response.status_code == 401


def test_ak_5_5_tek_gunluk_seride_degisim_null_doner(db_session, client_for):
    """Tek fiyat noktası varsa değişim hesaplanamaz.

    `0` dönseydi arayüz "bugün değişmedi" gösterirdi — olmayan bir bilgiyi
    uydurmak olurdu. `None` dönmeli, arayüz "—" göstermeli.
    """
    bugun = date.today()
    asset = _fiyatli_varlik(db_session, "TEK", [(bugun, 100)])
    user = _portfoy_kur(db_session, "piyasa-tek@example.com", asset)

    body = client_for(user).get(f"/api/market/influence/{user.id}").json()

    satirlar = {r["symbol"]: r for r in body["rows"]}
    assert satirlar["TEK"]["change_percent"] is None


def test_degisim_onceki_ISLEM_gununden_hesaplanir(db_session, client_for):
    """Aradaki günlerde fiyat yoksa (hafta sonu) bir önceki kayıtlı gün kullanılır.

    Takvim günü ("dün") aransaydı pazartesi günü değişim hep `null` çıkardı;
    borsa cumartesi-pazar kapalı.

    TARİHLER SABİT, `date.today()` DEĞİL. Göreli gün kullanan ilk sürüm
    testin koştuğu güne bağımlıydı: `price_service` seriden hafta sonlarını
    düşürüyor (`d.weekday() < 5`), dolayısıyla salı günü koşulduğunda
    "bugün − 3" cumartesiye denk gelip seride tek nokta kalıyor ve değişim
    `None` çıkıyordu. Yerelde pazartesi geçti, CI'da salı düştü. Pencere
    `as_of`'a (verideki en son fiyat günü) göre hesaplandığı için sabit
    geçmiş tarihler kullanmak güvenli.
    """
    cuma = date(2026, 8, 7)
    pazartesi = date(2026, 8, 10)
    asset = _fiyatli_varlik(db_session, "HFT", [(cuma, 100), (pazartesi, 110)])
    user = _portfoy_kur(db_session, "piyasa-hafta@example.com", asset)

    body = client_for(user).get(f"/api/market/influence/{user.id}").json()

    satirlar = {r["symbol"]: r for r in body["rows"]}
    assert satirlar["HFT"]["change_percent"] == pytest.approx(10.0)


def test_nakit_etki_listesinde_yer_almaz(db_session, client_for):
    """Nakdin fiyatı ve dolayısıyla günlük değişimi yok; satır israfı olur."""
    bugun = date.today()
    asset = _fiyatli_varlik(db_session, "NKT", [(bugun - timedelta(days=1), 100), (bugun, 105)])
    user = _portfoy_kur(db_session, "piyasa-nakit@example.com", asset)

    body = client_for(user).get(f"/api/market/influence/{user.id}").json()

    siniflar = {r["asset_class"] for r in body["rows"]}
    assert AssetClass.CASH.value not in siniflar


def test_gosterge_seridi_fiyat_tarihi_ve_kaynak_tasir(db_session, client_for):
    """AK 5.1 / 5.3: rakamın nereden geldiği ve hangi güne ait olduğu görünmeli."""
    bugun = date.today()
    _fiyatli_varlik(db_session, "XU100", [(bugun - timedelta(days=1), 14400), (bugun, 14514)])
    user = User(email="piyasa-gosterge@example.com", full_name="Gosterge")
    db_session.add(user)
    db_session.commit()

    response = client_for(user).get("/api/market/indicators")
    assert response.status_code == 200

    body = response.json()
    assert "indicators" in body and "as_of" in body
    gostergeler = {g["symbol"]: g for g in body["indicators"]}
    assert "XU100" in gostergeler
    for alan in ("symbol", "price", "price_date", "source", "stale", "change_percent"):
        assert alan in gostergeler["XU100"], alan


def test_ak_5_5_taninmayan_gosterge_ekrani_dusurmez(db_session, client_for):
    """Evren seed'lenmemişse şerit BOŞ döner, 404 değil.

    `get_current_prices` bu durumda `NotFoundError` fırlatıyor ve bu sohbet
    için doğru ("sorduğun sembolü tanımıyorum"), ama burada sembolleri
    kullanıcı seçmiyor — sabit liste. Tüm Piyasa ekranını düşürmek yerine
    eksikler bildirilir.
    """
    user = User(email="piyasa-bos@example.com", full_name="Bos Evren")
    db_session.add(user)
    db_session.commit()

    response = client_for(user).get("/api/market/indicators")

    assert response.status_code == 200
    body = response.json()
    assert body["indicators"] == []
    assert body["missing_symbols"], "eksik semboller sessizce yutulmamalı"
