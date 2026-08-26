"""Canlı makro haber katmanının testleri: sembol eşlemesi (universe.py),
yfinance haber ayrıştırma (yfinance_p.py), yazma (macro_news_ingest.py) ve
okuma (macro_news_service.py). MCP tool testleri tests/test_mcp_market_tool.py
içinde; ajan tarafı testleri tests/test_risk_agent.py içinde."""

from datetime import datetime, timedelta, timezone

from app.core.config import AssetClass
from app.models import MacroNewsSnapshot
from app.providers.base import NewsItem, ProviderError
from app.providers.universe import SPEC_BY_SYMBOL, macro_news_key, yfinance_news_ticker
from app.providers.yfinance_p import YFinanceProvider, _parse_news_item
from app.services.macro_news_ingest import run_macro_news_update, upsert_news
from app.services.macro_news_service import get_macro_news

# --- providers/universe.py: sembol -> haber anahtarı eşlemesi ---------------


def test_doviz_yf_symbol_ile_haber_ticker_i_cozer():
    spec = SPEC_BY_SYMBOL["USDTRY"]
    assert yfinance_news_ticker(spec) == "USDTRY=X"
    assert macro_news_key(spec) == "USDTRY"


def test_kiymetli_maden_provider_symbol_ile_haber_ticker_i_cozer():
    spec = SPEC_BY_SYMBOL["XAUTRY"]
    assert yfinance_news_ticker(spec) == "GC=F"
    assert macro_news_key(spec) == "XAUTRY"


def test_turetilmis_altin_sikkesi_tabaninin_haberine_eslenir():
    # CEYREK kendi ticker'ına sahip değil (DERIVED); haberi XAUTRY'nin
    # (gram altın) ticker'ından (GC=F) çekilir ama anahtar olarak XAUTRY
    # kullanılır — dört sikke türü de aynı satıra düşsün diye.
    spec = SPEC_BY_SYMBOL["CEYREK"]
    assert yfinance_news_ticker(spec) == "GC=F"
    assert macro_news_key(spec) == "XAUTRY"


def test_tefas_altin_fonu_gram_altinin_haberini_paylasir():
    # GTA (Garanti Portföy Altın Fonu) TEFAS üzerinden fiyatlanır, kendi
    # Yahoo ticker'ı yok — ama ekonomik riski gram altınla (XAUTRY) birebir
    # aynı olduğu için onun haberini paylaşmalı (gold coin'lerle aynı ilke).
    spec = SPEC_BY_SYMBOL["GTA"]
    assert yfinance_news_ticker(spec) == "GC=F"
    assert macro_news_key(spec) == "XAUTRY"


def test_hisse_icin_haber_anahtari_uretilmez():
    # Hisse zaten get_portfolio_news ile sembol bazlı kapsanıyor; burada
    # None dönmesi ikinci bir (gereksiz) haber çağrısını engeller.
    spec = SPEC_BY_SYMBOL["THYAO"]
    assert yfinance_news_ticker(spec) is None
    assert macro_news_key(spec) is None


def test_tahvil_fonu_icin_haber_anahtari_uretilmez():
    # TEFAS fonlarının Yahoo'da karşılığı yok.
    spec = SPEC_BY_SYMBOL["AK2"]
    assert yfinance_news_ticker(spec) is None


# 2026-08-26: "nakit icin haber anahtari uretilmez" testi buradan
# KALDIRILDI — MEVDUAT-V/MEVDUAT-VS universe.py'den tamamen kaldırıldı (bkz.
# o dosyadaki "Nakit" bolumu notu, AK 5.1): AssetClass.CASH artik evrende
# hicbir sentetik varlik tasimiyor, nakit yalnizca defterdeki serbest bakiye
# olarak temsil ediliyor. Test edilecek bir SPEC_BY_SYMBOL girdisi kalmadigi
# icin senaryonun kendisi anlamsizlasti.


# --- providers/yfinance_p.py: haber ayrıştırma -------------------------------


def test_yeni_semadaki_haber_ogesi_ayristirilir():
    # yfinance>=0.2.43: "content" altında iç içe, pubDate ISO metin.
    raw = {
        "content": {
            "title": "TCMB faiz kararını açıkladı",
            "pubDate": "2026-08-24T12:00:00Z",
            "provider": {"displayName": "Reuters"},
            "canonicalUrl": {"url": "https://example.com/haber-1"},
        }
    }
    item = _parse_news_item(raw)
    assert item == NewsItem(
        headline="TCMB faiz kararını açıkladı",
        source="Reuters",
        url="https://example.com/haber-1",
        published_at=datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc),
    )


def test_eski_semadaki_haber_ogesi_de_ayristirilir():
    # Sürüm geçişinde görülebilecek düz şema.
    raw = {
        "title": "Altın rekor kırdı",
        "link": "https://example.com/haber-2",
        "publisher": "Bloomberg HT",
        "providerPublishTime": 1755000000,  # unix saniye
    }
    item = _parse_news_item(raw)
    assert item is not None
    assert item.headline == "Altın rekor kırdı"
    assert item.source == "Bloomberg HT"
    assert item.url == "https://example.com/haber-2"
    assert item.published_at.tzinfo is not None


def test_zorunlu_alan_eksikse_haber_ogesi_atlanir():
    # Başlık/URL/tarihten biri eksikse uydurma yok — None döner, çağıran
    # taraf bu öğeyi sessizce atlar.
    assert _parse_news_item({"content": {"title": "Başlık var ama tarih yok"}}) is None
    assert _parse_news_item({"title": "Eski şema, tarih yok", "link": "https://x"}) is None
    assert _parse_news_item({}) is None


def test_yayin_yayincisi_yoksa_yahoo_finance_e_duser():
    raw = {
        "content": {
            "title": "Yayıncısız haber",
            "pubDate": "2026-08-24T12:00:00Z",
            "canonicalUrl": {"url": "https://example.com/haber-3"},
        }
    }
    item = _parse_news_item(raw)
    assert item is not None
    assert item.source == "Yahoo Finance"


def test_fetch_news_yfinance_ticker_i_cagirir_ve_siralar(monkeypatch):
    # En yeni -> en eski sıralanmalı ve limit uygulanmalı.
    import yfinance

    class _FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol
            self.news = [
                {
                    "content": {
                        "title": "Eski haber",
                        "pubDate": "2026-08-20T00:00:00Z",
                        "provider": {"displayName": "X"},
                        "canonicalUrl": {"url": "https://x/eski"},
                    }
                },
                {
                    "content": {
                        "title": "Yeni haber",
                        "pubDate": "2026-08-24T00:00:00Z",
                        "provider": {"displayName": "X"},
                        "canonicalUrl": {"url": "https://x/yeni"},
                    }
                },
            ]

    monkeypatch.setattr(yfinance, "Ticker", _FakeTicker)

    items = YFinanceProvider().fetch_news("GC=F", limit=1)

    assert len(items) == 1
    assert items[0].headline == "Yeni haber"


def test_fetch_news_saglayici_patlarsa_provider_error_firlatir(monkeypatch):
    import yfinance

    class _PatlayanTicker:
        def __init__(self, symbol):
            raise RuntimeError("network down")

    monkeypatch.setattr(yfinance, "Ticker", _PatlayanTicker)

    try:
        YFinanceProvider().fetch_news("GC=F")
    except ProviderError:
        pass
    else:
        raise AssertionError("ProviderError bekleniyordu")


# --- services/macro_news_ingest.py: yazma ------------------------------------


class _FakeNewsProvider:
    """YFinanceProvider'ın yerine geçer: gerçek ağ çağrısı yapmadan
    run_macro_news_update'in DB'ye yazma/temizleme davranışını test eder."""

    def __init__(self, by_ticker: dict[str, list[NewsItem]]):
        self._by_ticker = by_ticker
        self.calls: list[str] = []

    def fetch_news(self, ticker: str, limit: int = 5) -> list[NewsItem]:
        self.calls.append(ticker)
        if ticker == "SI=F":  # gümüş: kasıtlı olarak patlatılıyor (bkz. testler)
            raise ProviderError("fake", ticker, "kasten patlatıldı")
        return self._by_ticker.get(ticker, [])[:limit]


def _news_item(url: str, published_days_ago: int = 0) -> NewsItem:
    return NewsItem(
        headline=f"Haber {url}",
        source="Test Kaynağı",
        url=url,
        published_at=datetime.now(timezone.utc) - timedelta(days=published_days_ago),
    )


def test_upsert_news_ayni_url_tekrar_yazilmaz(db_session):
    fetched_at = datetime.now(timezone.utc)
    item = _news_item("https://x/1")

    written_first = upsert_news(db_session, "XAUTRY", AssetClass.PRECIOUS_METAL, [item], fetched_at)
    written_second = upsert_news(
        db_session, "XAUTRY", AssetClass.PRECIOUS_METAL, [item], fetched_at
    )
    db_session.commit()

    rows = db_session.query(MacroNewsSnapshot).filter_by(symbol="XAUTRY").all()
    assert written_first == 1
    assert written_second == 0  # aynı (symbol, url) — çakışma, atlanır
    assert len(rows) == 1


def test_run_macro_news_update_sembol_basina_bagimsiz_dener(db_session):
    # GC=F ve USDTRY=X basarili; SI=F (gümüş) FakeProvider tarafından kasten
    # patlatılıyor — bu yalnızca XAGTRY'yi atlamalı, tüm çalıştırmayı
    # düşürmemeli (zarif düşüş, price_ingest.py ile aynı ilke).
    provider = _FakeNewsProvider(
        {"GC=F": [_news_item("https://x/altin")], "USDTRY=X": [_news_item("https://x/dolar")]}
    )

    results = run_macro_news_update(db_session, provider=provider)

    statuses = {r["symbol"]: r["status"] for r in results}
    assert statuses["XAUTRY"] == "success"
    assert statuses["USDTRY"] == "success"
    assert statuses["XAGTRY"] == "failed"

    rows = db_session.query(MacroNewsSnapshot).all()
    written_symbols = {row.symbol for row in rows}
    assert "XAUTRY" in written_symbols
    assert "USDTRY" in written_symbols
    assert "XAGTRY" not in written_symbols


def test_run_macro_news_update_eski_satirlari_temizler(db_session, monkeypatch):
    from app.core import config as config_module

    monkeypatch.setattr(config_module.settings, "macro_news_retention_days", 1)

    db_session.add(
        MacroNewsSnapshot(
            symbol="XAUTRY",
            asset_class=AssetClass.PRECIOUS_METAL,
            headline="Çok eski haber",
            source="Test",
            url="https://x/cok-eski",
            published_at=datetime.now(timezone.utc) - timedelta(days=30),
            fetched_at=datetime.now(timezone.utc) - timedelta(days=30),
        )
    )
    db_session.commit()

    run_macro_news_update(db_session, provider=_FakeNewsProvider({}))

    kalan = db_session.query(MacroNewsSnapshot).filter_by(url="https://x/cok-eski").all()
    assert kalan == []


# --- services/macro_news_service.py: okuma -----------------------------------


def test_get_macro_news_eski_haberi_disliyor(db_session, monkeypatch):
    from app.core import config as config_module

    monkeypatch.setattr(config_module.settings, "macro_news_max_age_days", 3)

    db_session.add_all(
        [
            MacroNewsSnapshot(
                symbol="XAUTRY",
                asset_class=AssetClass.PRECIOUS_METAL,
                headline="Taze haber",
                source="Test",
                url="https://x/taze",
                published_at=datetime.now(timezone.utc) - timedelta(days=1),
                fetched_at=datetime.now(timezone.utc),
            ),
            MacroNewsSnapshot(
                symbol="XAUTRY",
                asset_class=AssetClass.PRECIOUS_METAL,
                headline="Bayat haber",
                source="Test",
                url="https://x/bayat",
                published_at=datetime.now(timezone.utc) - timedelta(days=10),
                fetched_at=datetime.now(timezone.utc),
            ),
        ]
    )
    db_session.commit()

    sonuc = get_macro_news(db_session, ["XAUTRY"])

    baslıklar = [h["headline"] for h in sonuc["XAUTRY"]]
    assert baslıklar == ["Taze haber"]


def test_get_macro_news_bos_sembol_listesi_bos_sozluk_doner(db_session):
    assert get_macro_news(db_session, []) == {}


def test_get_macro_news_hicbir_haberi_olmayan_sembolu_atlar(db_session):
    sonuc = get_macro_news(db_session, ["BILINMEYEN"])
    assert sonuc == {}
