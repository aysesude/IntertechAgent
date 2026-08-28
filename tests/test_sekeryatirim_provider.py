"""app/providers/sekeryatirim_p.py: Şeker Yatırım "Tavsiye Listesi" HTML
ayrıştırıcısı.

Sabit (canlı siteye gitmeyen) bir HTML örneği kullanılır — yapı 2026-08-28'de
gerçek sayfa fetch edilerek elle doğrulandı (bkz. modül docstring'i).
`monkeypatch` ile `requests.get` sahtelenir — projede dış HTTP çağrılarını
test etmenin yerleşik yolu bu (bkz. tests/test_macro_news_ingest.py).
"""

from decimal import Decimal

import pytest

from app.providers import sekeryatirim_p
from app.providers.base import ProviderError

_ORNEK_HTML = """
<html><body>
<p class="rapor-tarih">28.08.2026</p>
<table class="table table-striped sub-table tavsiyeListesi">
    <thead><tr><td>BANKA</td></tr></thead>
    <tbody>
        <tr>
            <td align="left">
GARAN                                                </td>
            <td align="right"><div class="al-icon">AL</div></td>
            <td align="right">
133,00                                                </td>
            <td align="right">
182,99                                                </td>
            <td align="right">378.820</td>
            <td align="right">503.152</td>
            <td align="right">32,8%</td>
            <td align="right">5,67</td>
            <td align="right">1,17</td>
        </tr>
        <tr>
            <td align="left">
VESBE                                                </td>
            <td align="right"><div class="gg-icon">G.G.</div></td>
            <td align="right">
5,28                                                </td>
            <td align="right">
-                                                </td>
            <td align="right">8.448</td>
            <td align="right">-</td>
            <td align="right">-</td>
            <td align="right">-</td>
            <td align="right">0,20</td>
        </tr>
    </tbody>
</table>
<table class="table table-striped sub-table tavsiyeListesi">
    <thead><tr><td>SANAYİ</td></tr></thead>
    <tbody>
        <tr>
            <td align="left">
ASELS                                                </td>
            <td align="right"><div class="al-icon">AL</div></td>
            <td align="right">
403,75                                                </td>
            <td align="right">
495,00                                                </td>
            <td align="right">1</td>
            <td align="right">1</td>
            <td align="right">1%</td>
            <td align="right">1</td>
            <td align="right">1</td>
        </tr>
    </tbody>
</table>
</body></html>
"""


class _SahteYanit:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}")


def test_fetch_target_prices_gercek_yapiyi_ayristirir(monkeypatch):
    monkeypatch.setattr(sekeryatirim_p.requests, "get", lambda *a, **k: _SahteYanit(_ORNEK_HTML))

    noktalar = sekeryatirim_p.fetch_target_prices()

    semboller = {p.symbol for p in noktalar}
    assert semboller == {"GARAN", "ASELS"}

    garan = next(p for p in noktalar if p.symbol == "GARAN")
    assert garan.institution == "Şeker Yatırım"
    assert garan.recommendation == "AL"
    assert garan.target_price == Decimal("182.99")
    assert garan.price_at_report == Decimal("133.00")
    assert garan.report_date.isoformat() == "2026-08-28"


def test_hedef_fiyati_olmayan_satir_uydurulmadan_atlanir(monkeypatch):
    """VESBE ("G.G." / "-") — hedef fiyat yok demek, tahmini bir değer
    yazılmaz (CLAUDE.md "Uydurmama"); satır tamamen atlanır."""
    monkeypatch.setattr(sekeryatirim_p.requests, "get", lambda *a, **k: _SahteYanit(_ORNEK_HTML))

    noktalar = sekeryatirim_p.fetch_target_prices()

    assert "VESBE" not in {p.symbol for p in noktalar}


def test_sayfa_erisilemezse_provider_error_firlatir(monkeypatch):
    monkeypatch.setattr(
        sekeryatirim_p.requests, "get", lambda *a, **k: _SahteYanit("", status_code=500)
    )

    with pytest.raises(ProviderError):
        sekeryatirim_p.fetch_target_prices()


def test_beklenmeyen_bos_sayfa_provider_error_firlatir(monkeypatch):
    """Sayfa alınır ama beklenen tablo/satır hiç bulunamazsa (yapı
    değişmiş olabilir) sessizce boş liste DÖNÜLMEZ — hata fırlatılır ki
    çağıran fark etsin."""
    monkeypatch.setattr(
        sekeryatirim_p.requests,
        "get",
        lambda *a, **k: _SahteYanit(
            '<html><body><p class="rapor-tarih">28.08.2026</p></body></html>'
        ),
    )

    with pytest.raises(ProviderError):
        sekeryatirim_p.fetch_target_prices()
