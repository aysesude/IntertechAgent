# Akıllı Kişisel Finans Danışmanı — Proje Talimatları

Yapay zekâ destekli kişisel finans danışmanı (InternTech 2026, demo/POC):
çoklu ajan mimarisi (Portföy, Piyasa/RAG, Risk) + FastAPI backend + React
dashboard + MCP server + PostgreSQL. Kullanıcı verisi sentetiktir; piyasa
fiyatları gerçek kaynaklardan toplanabilir.

## Önce oku

1. **`docs/DATA.md`** — veri katmanı el kitabı. Veriye dokunan HER işten önce
   zorunlu. Altın kurallar, işaret sözleşmesi ve "nasıl yapılır" tarifleri
   orada; burada tekrarlanmaz.
2. `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/AGENTS.md` — ilgili alanda
   çalışıyorsan.

## Komutlar

```bash
cp .env.example .env                 # ilk kurulumda
docker compose up -d postgres        # lokal DB (herkes kendi lokalinde)
docker compose exec api alembic upgrade head
make seed                            # sentetik evren + işlem defteri
make demo-users                      # demo kullanıcıların giriş bilgileri
make backfill                        # gerçek fiyat geçmişi (ağ gerekir)
make daily-update                    # günün gerçek fiyatları
make test / make lint                # pytest + ruff + black (+ eslint)
```

Docker olmadan: `.venv` + `PYTHONPATH=". backend"` ile `pytest -q` (testler
SQLite'ta koşar, Postgres gerekmez).

## Dizin haritası

```
backend/app/models/      SQLAlchemy modelleri (şemanın gerçeği)
backend/alembic/         migration zinciri (docs/DATA.md §7)
backend/app/providers/   piyasa verisi sağlayıcıları (SAF: DB importu yasak)
backend/app/services/    iş mantığı: ledger, valuation, price_ingest, portfolio
backend/app/api/         FastAPI uçları (iş mantığı içermez, servisi çağırır)
data/                    seed betikleri + backfill/daily_update CLI
agents/                  ajanlar + orchestrator (yeniden yazılacak — bkz. Durum)
mcp_server/              MCP tool'ları
rag/                     RAG pipeline (iskelet)
frontend/                React + TS + Tailwind (mevcut arayüz)
frontend-v2/             VİRA arayüzü — yan yana koşar, bkz. kendi README'si
tests/                   pytest; test adları kabul kriterine bağlanır
```

## Pazarlıksız kurallar

- **Veri yazma kapıları:** deftere yalnızca `ledger_service.record_transaction`,
  holdings'e yalnızca `rebuild_holdings`, fiyata yalnızca
  `price_ingest.upsert_prices` yazar. Başka yoldan yazma.
- **Para/fiyat = `Decimal`.** Float ile para taşıma.
- **Gizli bilgi yalnızca `.env`'de.** Koda bağlantı adresi/anahtar gömme —
  CI'da gitleaks taraması var, PR'ı düşürür.
- **Kod İngilizce** (isim, docstring, commit); **kullanıcıya görünen metin
  Türkçe** (₺/%, tutarlı biçim).
- **Finansal çıktılara** "Bu bir yatırım tavsiyesi değildir." uyarısı (sunum
  katmanında; tool çıktısına gömülmez).
- **Veri izolasyonu (AK 5.4):** kullanıcıya özel her uç `Depends(get_current_user)`
  + `verify_user_access(user_id, current_user)` ister (`app/api/deps.py`).
  Yeni bir `{user_id}` ucu yazıyorsan bu iki satır olmadan merge etme.
- **Uydurmama:** kaynağı olmayan değer üretme — eksik veriyi varsayımla
  doldurmak yerine `None`/uyarı döndür (AK 5.5, 5.10).
- **Zarif düşüş:** dış servis/DB hatasında çökme yok; anlamlı hata + son
  bilinen veriyle devam.
- **Boş/eksik veri:** boş portföy, sıfır değer, eksik fiyat senaryolarını
  her özellikte test et — demo'da en çok patlayan yerler bunlar.

## Çalışma düzeni

- Dal başına tek iş kolu; kısa ömürlü dallar; PR ile `test` dalına, oradan
  `main`'e. Migration eklerken zincirin ucuna ekle (`alembic heads` tek baş
  kalmalı); PG enum tuzakları için `docs/DATA.md` §8.
- Yeni yetenek eklerken hangi FR/US/AK'ya bağlandığını PR açıklamasına yaz;
  testi `test_ak_x_y_...` kalıbıyla adlandır (izlenebilirlik zinciri).
- Önce mevcut kodu oku, sonra öner, sonra yaz. Büyük değişiklikte önce plan
  sun. Bir şeyi "bitti" saymadan çalıştığını göster (test/çıktı).

## Durum (14 Ağustos 2026)

- **Veri katmanı tamam** (`veri-sistemi` dalı): ledger şeması, sağlayıcılar,
  ingest, defterden üretilen seed, okuma servisleri, 9 invariant testi.
- **Ajanlar yeniden yazılacak:** eski `ck_risk` dalı rafta (merge edilmeyecek);
  risk metodolojisi (SRRI bantları, kovaryans, VaR, ortak-gün kesişimi) doğru
  bulundu, yeniden yazımda örnek alınabilir. Ajanlar veriye
  `services/` üzerinden bağlanır: özet için `portfolio_service`, tarihsel
  değer/getiri için `valuation_service` (TWR), pozisyon/nakit için
  `ledger_service`.
- **RAG + Piyasa Ajanı iskelet** (`NotImplementedError`); Orchestrator niyet
  tespiti sabit `"portfolio"` döndürüyor.
- Merge sonrası herkes: `alembic upgrade head && make seed`.
