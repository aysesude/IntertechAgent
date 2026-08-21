"""Dashboard uçlarının testleri.

Vurgu iki noktada: uçların ajan/LLM çağırmadan servisleri doğrudan okuması ve
uygulama hatalarının doğru HTTP koduna çevrilmesi (404 / 409 / 422 birbirinden
farklı şeyler — arayüz üçünü ayrı göstermeli).
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.config import AssetClass
from app.main import app
from app.models import (
    Asset,
    Holding,
    Portfolio,
    PriceHistory,
    Transaction,
    TransactionType,
    User,
)


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def api_user(db_session):
    """1 Ocak'ta 1.000 TL ile 10 adet alınır, 9 Ocak'ta fiyat 130 olur."""
    user = User(email="api@example.com", full_name="Api")
    stock = Asset(symbol="TST", name="Test Hisse", asset_class=AssetClass.STOCK, currency="TRY")
    gold = Asset(
        symbol="XAUTRY", name="Gram Altin", asset_class=AssetClass.PRECIOUS_METAL, currency="TRY"
    )
    db_session.add_all([user, stock, gold])
    db_session.flush()

    portfolio = Portfolio(user_id=user.id)
    db_session.add(portfolio)
    db_session.flush()

    fiyatlar = {
        date(2026, 1, 1): "100",
        date(2026, 1, 2): "110",
        date(2026, 1, 5): "120",
        date(2026, 1, 9): "130",
    }
    db_session.add_all(
        [
            PriceHistory(asset_id=stock.id, price_date=gun, close_price=Decimal(deger))
            for gun, deger in fiyatlar.items()
        ]
        + [
            PriceHistory(asset_id=gold.id, price_date=date(2026, 1, 1), close_price=Decimal(1000)),
            PriceHistory(asset_id=gold.id, price_date=date(2026, 1, 9), close_price=Decimal(1100)),
            Holding(
                portfolio_id=portfolio.id,
                asset_id=stock.id,
                quantity=Decimal(10),
                avg_cost_price=Decimal(100),
            ),
            Transaction(
                portfolio_id=portfolio.id,
                transaction_type=TransactionType.DEPOSIT,
                quantity=Decimal(0),
                currency="TRY",
                fx_rate_to_try=Decimal(1),
                cash_amount_try=Decimal(1000),
                transaction_date=datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
            ),
            Transaction(
                portfolio_id=portfolio.id,
                asset_id=stock.id,
                transaction_type=TransactionType.BUY,
                quantity=Decimal(10),
                price=Decimal(100),
                currency="TRY",
                fx_rate_to_try=Decimal(1),
                cash_amount_try=Decimal(-1000),
                transaction_date=datetime(2026, 1, 1, 11, tzinfo=timezone.utc),
            ),
        ]
    )
    db_session.commit()
    return user


def test_holdings_endpoint_returns_rows_and_weights(client, api_user):
    response = client.get(f"/api/portfolio/{api_user.id}/holdings")
    assert response.status_code == 200

    body = response.json()
    assert body["holdings"][0]["symbol"] == "TST"
    # 10 x 130 = 1.300; nakit 0 -> agirlik %100. Money tipi float serialize edilir.
    assert body["holdings"][0]["market_value_try"] == 1300.0
    assert body["holdings"][0]["weight_percent"] == 100.0
    assert body["best_performer"]["symbol"] == "TST"


def test_performance_endpoint_accepts_window_and_strips_flows(client, api_user):
    response = client.get(f"/api/portfolio/{api_user.id}/performance", params={"window": "1m"})
    assert response.status_code == 200

    body = response.json()
    assert body["window"] == "1m"
    assert body["granularity"] == "daily"
    # 1.000 -> 1.300, donem ici para girisi yok.
    assert body["summary"]["change_amount"] == 300.0
    assert body["summary"]["change_percent"] == 30.0
    assert body["truncated_to_inception"] is True


def test_benchmark_endpoint_compares_with_index(client, api_user):
    response = client.get(f"/api/portfolio/{api_user.id}/benchmark", params={"window": "1m"})
    assert response.status_code == 200

    body = response.json()
    assert body["portfolio_return_percent"] == 30.0
    endeksler = {entry["symbol"]: entry["return_percent"] for entry in body["benchmarks"]}
    assert endeksler == {"XAUTRY": 10.0}


def test_transactions_endpoint_filters_by_date(client, api_user):
    hepsi = client.get(f"/api/portfolio/{api_user.id}/transactions")
    assert hepsi.status_code == 200
    assert len(hepsi.json()["transactions"]) == 2

    suzulmus = client.get(
        f"/api/portfolio/{api_user.id}/transactions", params={"start_date": "2026-02-01"}
    )
    assert suzulmus.status_code == 200
    assert suzulmus.json()["transactions"] == []


def test_transactions_endpoint_rejects_reversed_range_with_422(client, api_user):
    response = client.get(
        f"/api/portfolio/{api_user.id}/transactions",
        params={"start_date": "2026-02-01", "end_date": "2026-01-01"},
    )
    assert response.status_code == 422


def test_price_history_endpoint_reports_unknown_symbols(client, api_user):
    response = client.get(
        "/api/prices/history", params={"symbols": ["TST", "YOKBOYLE"], "window": "1m"}
    )
    assert response.status_code == 200

    body = response.json()
    assert body["unknown_symbols"] == ["YOKBOYLE"]
    assert len(body["series"]["TST"]) == 4
    # Canli fiyat degil: verinin hangi gune ait oldugu bildirilir.
    assert body["as_of"] == "2026-01-09"


def test_unknown_user_returns_404_not_409(client, db_session):
    missing = uuid.uuid4()
    for yol in ("", "/holdings", "/performance", "/benchmark", "/transactions"):
        response = client.get(f"/api/portfolio/{missing}{yol}")
        assert response.status_code == 404, yol


def test_portfolio_without_transactions_returns_409(client, db_session):
    """Kaynak var ama hesaplanacak veri yok — 404'ten farkli bir durum."""
    user = User(email="bos-api@example.com", full_name="Bos")
    db_session.add(user)
    db_session.flush()
    db_session.add(Portfolio(user_id=user.id))
    db_session.commit()

    response = client.get(f"/api/portfolio/{user.id}/performance")
    assert response.status_code == 409
