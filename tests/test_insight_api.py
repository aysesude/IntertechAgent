"""`GET /api/insight/{user_id}` — Hızlı Özet paneli.

Ajanın kendi testleri `tests/test_summary_agent.py`'de; burada yalnızca uç
sözleşmesi sınanıyor: veri izolasyonu (AK 5.4), kart sayısı/sırası ve
"panel hiçbir koşulda boş açılmaz" garantisi.
"""

import uuid

import pytest

from agents.summary_agent import KART_SIRASI
from app.models import User


@pytest.fixture()
def insight_user(db_session):
    user = User(email="insight@example.com", full_name="Insight")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def sahte_kartlar(monkeypatch):
    """Ajanı sahteler; uç testleri LLM'e ve MCP'ye gitmemeli."""

    def _kur(kartlar=None, hata: Exception | None = None):
        async def _uret(self, user_id):
            if hata is not None:
                raise hata
            return (
                kartlar
                if kartlar is not None
                else [
                    {"id": kart_id, "title": kart_id, "body": "metin", "degraded": False}
                    for kart_id in KART_SIRASI
                ]
            )

        monkeypatch.setattr("agents.summary_agent.SummaryAgent.kartlari_uret", _uret)

    return _kur


def test_dort_kart_sirasiyla_doner(client_for, insight_user, sahte_kartlar):
    sahte_kartlar()
    response = client_for(insight_user).get(f"/api/insight/{insight_user.id}")

    assert response.status_code == 200
    body = response.json()
    assert [k["id"] for k in body["cards"]] == list(KART_SIRASI)
    assert body["user_id"] == str(insight_user.id)
    assert body["generated_at"]


def test_ak_5_4_baskasinin_ozeti_okunamaz(client_for, insight_user, db_session, sahte_kartlar):
    """Kullanıcıya özel her uç sahiplik doğrular (AK 5.4)."""
    sahte_kartlar()
    baskasi = User(email="baska@example.com", full_name="Baska")
    db_session.add(baskasi)
    db_session.commit()

    response = client_for(baskasi).get(f"/api/insight/{insight_user.id}")

    assert response.status_code == 403


def test_kimliksiz_erisim_reddedilir(client_for, insight_user, sahte_kartlar):
    sahte_kartlar()
    response = client_for().get(f"/api/insight/{insight_user.id}")

    assert response.status_code in (401, 403)


def test_ajan_patlarsa_panel_yine_de_DORT_KART_doner(client_for, insight_user, sahte_kartlar):
    """Boş panel göstermek kullanıcıya "özet yok" der; doğru bilgi "şu an
    üretilemedi"dir. Beklenmeyen bir istisnada bile dört kart dönmeli."""
    sahte_kartlar(hata=RuntimeError("beklenmeyen"))

    response = client_for(insight_user).get(f"/api/insight/{insight_user.id}")

    assert response.status_code == 200
    kartlar = response.json()["cards"]
    assert [k["id"] for k in kartlar] == list(KART_SIRASI)
    assert all(k["degraded"] for k in kartlar)
    assert all("üretilemedi" in k["body"] for k in kartlar)


def test_bilinmeyen_kullanici_404(client_for, insight_user, sahte_kartlar):
    sahte_kartlar()
    response = client_for(insight_user).get(f"/api/insight/{uuid.uuid4()}")

    assert response.status_code == 403
