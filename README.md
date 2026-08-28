# Akıllı Kişisel Finans Danışmanı

Kullanıcının portföyünü (hisse, altın, döviz, tahvil, fon) analiz eden, finansal
belgeleri RAG ile okuyan, KAP ve piyasa gündemini canlı çeken, risk
değerlendirmesi ve yeniden dengeleme önerisi sunan çoklu-ajan bir web
uygulaması. Kullanıcı Türkçe soruyor; orkestratör soruyu hangi ajanın
yanıtlayacağına kendisi karar veriyor ve yanıtları tek metinde birleştiriyor.

**Durum:** uçtan uca çalışıyor, iki ortamda canlı. Üç ajan da devrede, RAG
dolu, canlı veri kaynakları bağlı.

| Ortam | Adres | Branch |
|---|---|---|
| Test | https://test.34.159.243.0.nip.io (şifre korumalı) | `test` |
| Canlı | https://virafinance.org | `main` |

İki ortam **ayrı veritabanları** kullanır. Testte açılan hesap canlıda yoktur;
bu kasıtlıdır, sentetik test verisi demo ortamına sızmamalıdır.

Her ikisi de PR merge'iyle kendiliğinden güncellenir (`.github/workflows/deploy.yml`);
kimsenin sunucuya girmesi gerekmez. Çalışma düzeni: [docs/EKIP-OZETI.md](docs/EKIP-OZETI.md).

Ayrıntılı dokümanlar: [ARCHITECTURE](docs/ARCHITECTURE.md) ·
[DATA](docs/DATA.md) · [API](docs/API.md) · [AGENTS](docs/AGENTS.md) ·
[MCP-TOOLS](docs/MCP-TOOLS.md)

## Neyi nasıl yapıyor

**Üç ajan, bir orkestratör.** `agents/orchestrator.py` (LangGraph) önce kural
tabanlı bir kapsam kontrolünden geçirir, sonra LLM ile niyeti sınıflandırır ve
ilgili ajan(lar)ı **paralel** çalıştırıp yanıtları birleştirir.

| Ajan | Ne yapar | Veri kaynağı |
|---|---|---|
| **Portföy** | değer, dağılım, getiri, işlem geçmişi, endeks kıyası | Postgres (ledger'dan üretilir) |
| **Piyasa** | fiyat/kur, bilanço ve şirket profili, canlı KAP bildirimi, canlı piyasa gündemi | `price_history` + RAG + KAP + BloombergHT |
| **Risk** | volatilite, VaR, Sharpe, yoğunlaşma, yeniden dengeleme senaryoları | `app/services/risk_service.py` |

**Sayısal hiçbir değer LLM tarafından üretilmez.** Rakamlar servis
hesaplarından ve MCP tool çıktılarından gelir; LLM yalnızca eldeki veriyi
Türkçeleştirir. Kaynağı olmayan değer üretilmez, eksik veri varsayımla
doldurulmaz — hesaplanamayan bir metrik "hesaplanamadı" olarak döner.

**Arşiv ile canlı veri ayrıdır.** RAG yalnızca değişmeyecek belgeleri tutar
(67 doküman: çeyrek bilançoları, 31 şirket profili, TFRS referansları). Güncel
bilgi soru anında canlı çekilir ve yanıtta **kendi etiketli bloğunda** kalır,
LLM'den geçmez:

- `Güncel KAP Bildirimleri:` — şirket sorulduğunda, `pykap` ile KAP'tan
- `Güncel Piyasa Başlıkları:` — genel gündem sorulduğunda, BloombergHT'den

Dış kaynak düşerse blok sessizce atlanır; ana cevap ayakta kalır.

**Yatırımcı profili ölçülür, sorulmaz.** Hesap açma iki adımdır (kimlik +
açılış aktarımı); 18 soruluk SPK/TSPB uyumluluk anketi **ilk girişte**
kapatılamaz bir ekranda doldurulur. Anket kayıt akışının içindeyken yarıda
bırakılması hesabın hiç açılmamasına yol açıyordu — en pahalı adım en
kırılgan adıma bağlıydı.

Skorlama sunucudadır (`app/services/survey_service.py`); istemcinin
gönderdiği puana güvenilmez. Üç boyut ayrı ölçülür ve **nihai puan
`min(kapasite, tolerans)`** olur — ortalanmaz: parası olmayan cesur yatırımcı
ile parası olan ama düşüşe dayanamayan yatırımcı aynı profile düşmemelidir.
Bilgi puanı profile tavan uygular. Beyanlar birbiriyle çelişiyorsa (TK1)
profil **üretilmez**: çelişkiden türetilmiş bir profil, üretilmemiş profilden
kötüdür. Kullanıcıya hangi çelişkinin engellediği gösterilir ve cevaplarına
döner.

Açılış aktarımı ("başka bankadan para getir") gerçek bir para hareketi
değildir: girilen tutar deftere bir `DEPOSIT` işlemi olarak yazılır, bakiye
de her yerde olduğu gibi defterden üretilir.

## Teknoloji yığını

- Backend: Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic
- Veritabanı: PostgreSQL 16 · Vektör DB: Chroma 0.5.5
- Ajanlar: LangGraph · Tool katmanı: fastmcp (MCP)
- LLM: `app/core/llm_client.py` üzerinden soyutlanmış — `.env`'deki
  `LLM_PROVIDER` ile `openai` / `azure` / `ollama` arasında geçilir. Canlı
  ortamda OpenAI (`gpt-5.6-luna`), yerelde Ollama kullanılabilir.
- Frontend: React 18 + Vite + TypeScript, Tailwind, Recharts, TanStack Query
- Test: pytest (44 dosya, ~490 test) + vitest (22 dosya) · Lint: ruff + black + eslint

## Sıfırdan kurulum

```bash
git clone <repo-url> && cd finans-danismani
cp .env.example .env
```

`.env` içinde en az `JWT_SECRET_KEY` doldurulmalı (varsayılanı yok, bilerek).
LLM için ya `OPENAI_API_KEY` verin ya da `LLM_PROVIDER=ollama` bırakıp host
makinede `ollama serve` çalıştırın.

```bash
docker compose up --build postgres chroma api mcp_server frontend-v2
```

Servisler ayaktayken **ayrı bir terminalde**:

```bash
docker compose exec api alembic upgrade head
make seed                      # sentetik evren + işlem defteri
docker compose exec -w / api python -m rag.ingest   # RAG belgelerini indeksle
```

Artık:

- Arayüz: http://localhost:5173
- API dokümantasyonu: http://localhost:8000/docs
- Health check: http://localhost:8000/health
- Adminer (DB arayüzü): http://localhost:8080

### Giriş bilgileri

Kimlik doğrulama devrede — Dashboard artık kullanıcı ID'si sormuyor. Demo
kullanıcılarının T.C. kimlik numarası ve ortak şifresi için:

```bash
make demo-users
```

Liste `— (giriş yok)` diyorsa o ortamda kimlik ve şifre alanları hiç
doldurulmamıştır (migration bunları `NULL` ekler, bcrypt özeti migration
içinde üretilemez) ve **hiç kimse giriş yapamaz**. Düzeltmesi:

```bash
make credentials    # yalnızca eksik iki alanı doldurur, veri silmez
```

Ya da `virafinance.org` üzerinden "Üye ol" ile yeni bir hesap açın; anket
ilk girişte karşınıza çıkar.

## Makefile kısayolları

```bash
make up            # docker compose up --build
make seed          # sentetik evren + işlem defteri (VERİYİ SİLER)
make credentials   # mevcut kullanıcılara giriş bilgisi atar, veriyi silmeden
make demo-users    # demo kullanıcılarının giriş bilgileri
make backfill      # gerçek fiyat geçmişi (365 gün, ağ gerekir)
make daily-update  # günün gerçek fiyatları
make data-doctor   # maliyet/değerleme tutarlılık kontrolü (sadece okur)
make test          # pytest
make lint          # ruff + black + eslint
```

> `make seed` **tüm kullanıcı verisini** (sohbet geçmişi dahil) siler. Canlı ya
> da test ortamında migration sonrası `make credentials` kullanın.

## Testleri çalıştırma

Konteyner içinde (tam bağımlılıkla):

```bash
make test
```

Kendi makinenizde — testler geçici bir SQLite dosyasında koşar, Postgres
gerekmez (`tests/conftest.py` otomatik ayarlar):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
PYTHONPATH=". backend" pytest -q
```

Push öncesi üçünü birden koşmak CI'da sürpriz bırakmaz:

```bash
black . && ruff check . && PYTHONPATH=". backend" pytest -q
```

## Proje yapısı

```
finans-danismani/
  backend/app/api/        FastAPI uçları (iş mantığı içermez, servisi çağırır)
  backend/app/models/     SQLAlchemy modelleri (şemanın gerçeği)
  backend/app/services/   iş mantığı: ledger, valuation, price_ingest, portfolio, risk
  backend/app/providers/  piyasa verisi sağlayıcıları (yfinance, TCMB, TEFAS, KAP, BloombergHT)
  backend/alembic/        migration zinciri
  agents/                 üç ajan + LangGraph orkestratör + kural tabanlı sorgu ayrıştırma
  mcp_server/             MCP Server + 13 tool
  rag/                    ingest / retriever / vector_store
  data/                   seed betikleri, backfill/daily_update CLI, documents/ (67 .md)
  frontend-v2/            VİRA arayüzü — tek arayüz (React + Vite + TS)
  tests/                  pytest; test adları kabul kriterlerine bağlanır
  docs/                   ARCHITECTURE, DATA, API, AGENTS, MCP-TOOLS, EKIP-OZETI
```

## API uçları

| Uç | Açıklama |
|---|---|
| `POST /api/auth/login` · `GET /api/auth/me` | kimlik doğrulama (JWT) |
| `POST /api/auth/register` | hesap açma + portföy + açılış aktarımı (tek işlem) |
| `POST /api/auth/password-reset/{request,complete}` | şifre yenileme |
| `GET /api/survey/questions` | anket soruları (oturum istemez) |
| `POST /api/survey/score` | skorlar, kaydetmez |
| `POST /api/survey/submit/{user_id}` | skorlar ve profili kullanıcıya yazar |
| `POST /api/chat` | sohbet — Orchestrator → ajanlar → SSE stream |
| `GET /api/chat/sessions/{id}/messages` | oturum geçmişi |
| `GET /api/portfolio/{user_id}` | portföy özeti |
| `GET /api/portfolio/{user_id}/holdings` | varlık kırılımı |
| `GET /api/portfolio/{user_id}/performance` | dönemsel getiri (TWR) |
| `GET /api/portfolio/{user_id}/transactions` | işlem geçmişi |
| `GET /api/portfolio/{user_id}/benchmark` | endeks kıyaslaması |
| `GET /api/risk/{user_id}` | risk değerlendirmesi |
| `GET /api/users/{user_id}/risk-profile` · `PUT` | risk profili oku/güncelle |
| `GET /api/users/{user_id}/risk-survey` · `PUT` | anket puanı oku/güncelle |
| `GET /api/trade/{user_id}/assets` | işlem yapılabilir varlıklar |
| `POST /api/trade/{user_id}/preview` · `execute` | emir önizleme / deftere yazma |
| `POST /api/trade/{user_id}/deposit` | nakit girişi (defter işlemi) |
| `GET /api/market/indicators` | gösterge şeridi (fiyat + günlük değişim) |
| `GET /api/market/headlines` | canlı piyasa gündemi (BloombergHT) |
| `GET /api/market/influence/{user_id}` | pozisyonların ağırlığı ve günlük değişimi |
| `GET /api/market/calendar/{user_id}` | hisselerinin yaklaşan KAP bildirimleri |

Kullanıcıya özel her uç `Depends(get_current_user)` + `verify_user_access`
ister — veri izolasyonu tek bir kapıdan geçer (`app/api/deps.py`).

Sözleşme ayrıntıları: [docs/API.md](docs/API.md).

## MCP tool'ları

`get_portfolio_summary` · `get_holdings` · `get_portfolio_performance` ·
`get_transactions` · `get_benchmark_comparison` · `get_portfolio_news` ·
`get_current_prices` · `get_asset_price_history` · `search_market_news` ·
`get_macro_news` · `get_risk_assessment` · `get_live_kap_disclosures` ·
`get_live_market_headlines`

Tool docstring'leri dokümantasyon değil **prompt parçasıdır**: ajan seçimini
`client.list_tools()` ile okuduğu bu metinlere bakarak yapar. Ayrıntı:
[docs/MCP-TOOLS.md](docs/MCP-TOOLS.md).

## Kapsam dışı

- Gerçek para hareketi, emir iletimi, aracı kurum entegrasyonu — arayüzdeki
  alım/satım ve "başka bankadan para getir" adımları yalnızca **deftere işlem
  yazar**, dışarıya hiçbir talimat gitmez, banka bilgisi istenmez
- Gelecek fiyat/getiri tahmini — sorulduğunda açıkça reddedilir
- Kripto, türev ve gayrimenkul varlık sınıfları
- Çoklu sohbet oturumu arayüzü (liste/arama/silme)

Kullanıcı verisi **sentetiktir**; piyasa fiyatları gerçek kaynaklardan
toplanabilir (`make backfill`). Finansal çıktılara "Bu bir yatırım tavsiyesi
değildir." uyarısı eklenir.

## Sorun giderme

**Sohbet "Sorunuzu anlayamadım" diyor.** Niyet tespiti LLM çağrısı düşmüştür.
Logdan doğrulayın: `docker compose logs api | grep "niyet tespiti"`. Sebebi
genelde LLM sağlayıcısıdır — anahtar süresi dolmuş ya da kota bitmiştir.

**LLM 400 dönüyor.** `gpt-5.6-luna` yalnızca varsayılan `temperature`
değerini kabul ediyor; `.env`'de `OPENAI_TEMPERATURE=1` olmalı.

**"Veritabanımızda bu sorguyla ilgili doğrulanmış bir bilgi bulunamadı".**
Chroma boş olabilir. `rag.ingest` her çalıştığında koleksiyonu silip yeniden
kurar, sonrasında `mcp_server` yeniden başlatılmalıdır (bellekte eski
koleksiyona referans tutuyor) — deploy akışı ikisini de yapar.

**CORS hatası.** `CORS_ORIGINS` (.env) ile arayüzün gerçekte servis edildiği
origin birebir eşleşmeli; `localhost:5173` ile `127.0.0.1:5173` tarayıcı için
farklı origin'dir.

**Deploy geçti ama değişiklik görünmüyor.** Compose aynı `:latest` etiketine
yazdığı için çalışan konteyneri değişmemiş sayabiliyor; deploy bu yüzden
`--force-recreate -V` kullanıyor. Elle müdahale ederken aynı bayrakları verin.

### Neden ayrı bir Ollama container'ı yok

Ollama'yı konteynerize etmek ek imaj boyutu ve model indirme karmaşıklığı
getiriyor; host makinede çalıştırılması tercih edildi. İsterseniz
`docker-compose.yml`'a bir `ollama` servisi ekleyip `OLLAMA_BASE_URL`'i
güncelleyebilirsiniz.
