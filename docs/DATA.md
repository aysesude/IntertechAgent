# Veri Katmanı El Kitabı

> Hedef kitle: bu projeye ilk gün katılan geliştirici. Bu sayfayı okuduktan
> sonra veri katmanını kullanmak için kimseye soru sormanız gerekmemeli.
> Tasarım gerekçeleri için kök dizindeki `DB-PLANI.md` + `VERI-KATMANI-PLANI.md`.

## 1. Tek cümlelik model

**`transactions` yazılan gerçektir (append-only defter); `holdings` ondan
türetilen önbellektir; `price_history` dış dünyadır. Üçü birbirine karışmaz.**

```
providers/  (TCMB, yfinance, TEFAS, İş Portföy)      kullanıcı işlemleri
        │                                                   │
        ▼                                                   ▼
services/price_ingest.py  ──► price_history      ledger_service.record_transaction
   (kaynak öncelikli upsert)      │                  ──► transactions (append-only)
                                  │                         │
                                  │                         ▼
                                  │              ledger_service.rebuild_holdings
                                  │                  ──► holdings (önbellek)
                                  ▼                         │
                        valuation_service  ◄────────────────┘
                 (değer serisi, TWR, K/Z, kur dönüşümü)
```

## 2. Altın kurallar (ihlal = kırmızı test)

1. **Deftere yalnızca `ledger_service.record_transaction` yazar.** UPDATE ve
   DELETE yok; düzeltme ters kayıtla yapılır.
2. **`holdings`'i yalnızca `rebuild_holdings` yazar.** Elle holdings yazan kod
   `test_ledger_reconciliation`'ı kırar.
3. **`price_history`'ye yalnızca `price_ingest.upsert_prices` yazar.** Upsert
   önceliği: `synthetic(0) < derived(1) < yfinance(2) < tefas/isportfoy(3) <
   tcmb(4)`. Gerçek veri sentetiği ezer; sentetik gerçeği **asla** ezemez.
4. **Fiyat/para her zaman `Decimal`**; float yasak.
5. **Sağlayıcılar (providers/) saftır:** DB'ye dokunmaz, `except: pass` yapmaz,
   hata durumunda `ProviderError` fırlatır.
6. **Kod İngilizce, kullanıcıya dönen metin Türkçe.** Kaynak/kimlik bilgisi
   yalnızca `.env`'de (CI'da gitleaks taraması var).

## 3. İşaret sözleşmesi (transactions)

- `quantity` her zaman ≥ 0; yön `transaction_type`'tan okunur.
- `cash_amount_try` işaretlidir: **BUY/WITHDRAW/FEE → negatif**,
  **SELL/DEPOSIT/DIVIDEND/INTEREST → pozitif**.
- Nakit bakiyesi = `SUM(cash_amount_try)`; hiçbir anda negatif olamaz
  (`record_transaction` kontrol eder).
- `fx_rate_to_try` işlem anındaki kurdur ve dondurulur; `avg_cost_price` TRY
  cinsinden, komisyon dahil birim maliyettir.
- DEPOSIT/WITHDRAW/INTEREST/FEE varlığa bağlanmaz (`asset_id NULL`);
  BUY/SELL/DIVIDEND varlık ister (CHECK ile zorlanır).

## 4. Nasıl yapılır?

### Lokal kurulum
```bash
cp .env.example .env       # gerekirse EVDS_API_KEY doldurun
docker compose up -d postgres
docker compose exec api alembic upgrade head
make seed                  # 50 kullanıcı + sentetik fiyat + işlem defteri
```
Docker yoksa: `.venv` ile `alembic upgrade head && python -m data.generate_dummy`
(pytest `PYTHONPATH=. backend` ile SQLite üzerinde koşar: `pytest -q`).

### Gerçek fiyat verisi çekmek
```bash
make backfill              # bir kerelik: 365 günlük gerçek geçmiş
make daily-update          # her gün: günün fiyatları (cron'a bağlanacak iş)
```
Sonuçlar `data_ingest_log`'a yazılır. Başarısız kaynak DB'deki son veriyi
bozmaz; `make seed` de birikmiş gerçek veriyi silemez (öncelik kuralı).

### Yeni varlık eklemek
`backend/app/providers/universe.py` → `ASSET_UNIVERSE`'e bir `AssetSpec`
satırı ekleyin, `make seed` çalıştırın. **Başka hiçbir kod değişmez.**
Sağlayıcı eşlemesi (`data_source`, `provider_symbol`) spec'in içindedir.

### Yeni veri sağlayıcısı eklemek
1. `backend/app/providers/` altına yeni dosya: `fetch_series`/`fetch_latest`
   sunan bir sınıf (bkz. `base.py` sözleşmesi; `tcmb.py` örnek).
2. `config.py`'deki `PriceSource`'a değer + `PRICE_SOURCE_PRIORITY`'ye öncelik
   ekleyin (migration: enum'a değer eklemek gerekir — `d17f3b9e5c28`'deki tip
   yeniden yaratma kalıbını kopyalayın).
3. `registry.py`'de ilgili zincire yerleştirin.

### İşlem kaydetmek (ajan/API kodu)
```python
from app.services.ledger_service import record_transaction, rebuild_holdings

record_transaction(db, portfolio_id, TransactionType.BUY,
                   transaction_date=..., asset_id=..., quantity=..., price=...,
                   fx_rate_to_try=...)   # nakit ayağı otomatik hesaplanır
rebuild_holdings(db, portfolio_id)       # önbelleği tazele
```

### Portföy okumak
- Özet: `portfolio_service.get_portfolio_summary` (kur dönüşümü + nakit dahil)
- Tarihsel değer/getiri: `valuation_service.value_series` / `twr`
- Kâr/zarar: `valuation_service.realized_pnl` / `unrealized_pnl`
- Pozisyon/nakit (tarihli): `ledger_service.position_as_of` / `cash_balance_as_of`

## 5. Seed ve determinizm

- `SEED=42`, `ANCHOR_DATE` (.env, varsayılan 2026-08-01) — `date.today()`
  kullanılmaz; her çalıştırma aynı evreni üretir.
- Fiyatlar yalnızca **işlem günlerinde** (hafta içi) üretilir; gerçek
  kaynaklarla takvim uyumu için.
- Sentetik fiyatlar üç bileşenli **faktör modeli** kullanır (piyasa + sınıf +
  varlığa özgü); piyasa faktörü, DB'de gerçek USDTRY serisi varsa ondan
  türetilir. Korelasyonlar `test_synthetic_correlation_nonzero` ile korunur.
- `python -m data.generate_dummy` varsayılan olarak yalnızca kullanıcı
  tablolarını + sentetik fiyatları tazeler; `--wipe-all` her şeyi siler.

## 6. Değişmezler ve testleri (`tests/test_data_layer.py`)

| Değişmez | Test | Kriter |
|---|---|---|
| holdings == defterden yeniden üretilen | `test_ledger_reconciliation` | AK 5.12 |
| Nakit asla negatif değil | `test_cash_never_negative` | — |
| Sentetik gerçeği ezemez | `test_synthetic_never_overwrites_real` | AK 5.1/5.5 |
| Her fiyatta kaynak + zaman | `test_ak_5_3_price_source_and_timestamp` | AK 5.3 |
| USD varlık güncel kurla TRY'ye | `test_ak_5_7_fx_conversion` | AK 5.7 |
| DEPOSIT getiri sayılmaz (TWR) | `test_external_flow_excluded_from_return` | FR-3 |
| Türetilmiş fiyat = kaynak × katsayı | `test_derived_price_matches_factor` | — |
| Sentetik korelasyon ≠ 0 | `test_synthetic_correlation_nonzero` | AK-2.2/2.6 |

## 7. Şema özeti (migration zinciri)

`60bf3d7b4c54 → abe38b185ff1 → 9c31e7a0d2b4 → 4e8b2f6c1a53 → d17f3b9e5c28 → 6a92d4c8e0f1`

- `users` +risk_profile · `assets` +sub_type/is_active/data_source/
  provider_symbol/derived_from/derived_factor
- `price_history` +source/fetched_at, 18,6 hassasiyet
- `transactions` 7 tip + nakit ayağı + kur + CHECK'ler + indeksler
- `holdings` +realized_pnl_try/last_rebuilt_at (qty=0 satır silinmez)
- `data_ingest_log` (yeni): çekim işlerinin iş-düzeyi kaydı

## 8. Sık düşülen tuzaklar

- **PG enum'una `ADD VALUE` ile eklenen değer aynı transaction'da
  kullanılamaz.** Migration'da yeni değere başvuracaksanız tip yeniden
  yaratma kalıbını kullanın (`d17f3b9e5c28`).
- **Testler migration koşmaz** (`Base.metadata.create_all` + SQLite): CHECK
  kısıtlarını hem modele hem migration'a yazın.
- **`holdings.quantity == 0` satırı silmeyin** — gerçekleşmiş K/Z oradadır.
- **Tarihsel değerlemede bugünün kurunu kullanmayın**; `valuation_service`
  o günün kurunu kullanır, siz de öyle yapın.
