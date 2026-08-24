# Akıllı Kişisel Finans Danışmanı

Kullanıcının portföyünü (hisse, altın, döviz, tahvil) analiz eden, finansal haber
ve raporları RAG ile okuyan, risk değerlendirmesi ve yeniden dengeleme önerisi
sunan, çoklu-ajan mimarili bir web uygulaması.

**Durum:** walking skeleton — uçtan uca ince bir dilim çalışıyor (bkz. [Kapsam](#bu-aşamada-kapsamda-olan--olmayan)).
Mimari detaylar için [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), API sözleşmesi
için [docs/API.md](docs/API.md), ajan mimarisi için [docs/AGENTS.md](docs/AGENTS.md).

## Teknoloji yığını

- Backend: Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic
- Veritabanı: PostgreSQL 16
- Vektör DB: Chroma (yerel geliştirme; `rag/vector_store.py` üzerinden soyutlanmış)
- Agent framework: LangGraph, MCP: fastmcp
- LLM: Ollama (`app/core/llm_client.py` üzerinden; `.env` ile openai/azure/ollama arasında değiştirilebilir)
- Frontend: React 18 + Vite + TypeScript, Tailwind, Recharts, TanStack Query
- Test: pytest (backend)

## Ön koşullar

- Docker Desktop
- [Ollama](https://ollama.com) — host makinenizde çalışır olmalı (docker-compose'a
  dahil edilmedi, bkz. [Neden ayrı bir Ollama container'ı yok](#neden-ayrı-bir-ollama-containerı-yok))

## Sıfırdan kurulum

```bash
git clone <repo-url> && cd finans-danismani
```

```bash
cp .env.example .env
```

```bash
ollama serve
```

```bash
ollama pull qwen2.5:3b
```

```bash
docker compose up --build postgres chroma api frontend
```

İlk build birkaç dakika sürebilir. Servisler ayaktayken, **ayrı bir terminalde**:

```bash
docker compose run --rm api alembic upgrade head
```

```bash
make seed
```

(`make seed`, `docker compose exec api python -m data.generate_dummy` çalıştırır —
50 kullanıcı, kullanıcı başına 5-15 varlık, 12 aylık işlem geçmişi ve fiyat
serisi üretir; sabit seed ile deterministiktir, tekrar çalıştırılabilir.)

Artık:

- Frontend: http://localhost:5173 — bir kullanıcı ID'si girin (aşağıya bakın)
- API dokümantasyonu: http://localhost:8000/docs
- Health check: http://localhost:8000/health

### Dashboard'da kullanıcı ID'si nereden bulunur

Kimlik doğrulama bu aşamada kapsam dışı olduğu için Dashboard basit bir
"Kullanıcı ID" alanı ister. `make seed` sonrası DB'den bir ID alın:

```bash
docker compose exec postgres psql -U finans -d finans_danismani -c "SELECT id, email FROM users LIMIT 5;"
```

### MCP Server'ı da ayağa kaldırmak isterseniz

```bash
docker compose up mcp_server
```

`get_portfolio_summary` tool'unu servis eder, `http://localhost:8100/mcp` üzerinde
dinler. Ajanlar (`agents/portfolio_agent.py`) buna docker ağı üzerinden
(`http://mcp_server:8100/mcp`) bağlanır — API servisinin bunu kullanması için
ayrıca başlatmanız gerekmez, `POST /api/chat` zaten arka planda bu servise bağlanır.

## Testleri çalıştırma

```bash
docker compose exec api pytest
```

ya da kendi makinenizde (Postgres yerine geçici SQLite ile, `tests/conftest.py`
otomatik ayarlar):

```bash
cd backend && pip install -r requirements.txt
```

```bash
cd .. && pytest
```

## Makefile kısayolları

```bash
make up      # docker compose up --build
make seed    # dummy veri üret
make test    # pytest
make lint    # ruff + black + eslint
```

## Proje yapısı

```
finans-danismani/
  backend/app/       # FastAPI: api/, models/, schemas/, services/, core/
  backend/alembic/   # DB migration'ları
  agents/            # BaseAgent, PortfolioAgent (çalışıyor), Market/Risk (iskelet), Orchestrator
  mcp_server/        # MCP Server + tools/
  rag/               # RAG pipeline iskeleti (vector_store, ingest, retriever)
  data/              # generate_dummy.py
  frontend-v2/       # VİRA arayüzü (React + Vite + TS) — tek arayüz
  tests/             # pytest
  docs/              # ARCHITECTURE.md, API.md, AGENTS.md
```

## Bu aşamada kapsamda olan / olmayan

**Çalışıyor:**
- `GET /api/portfolio/{user_id}` — gerçek DB'den portföy özeti
- `POST /api/chat` — Orchestrator → Portföy Ajanı → MCP tool → SSE stream
- Sohbet geçmişi kalıcı (`ChatSession`/`Message`), son N mesaj Orchestrator'a bağlam olarak geçiyor
- MCP `get_portfolio_summary` tool'u
- Frontend Dashboard: gerçek veriyle pasta grafiği + çalışan chat kutusu

**Kasıtlı olarak iskelet / kapsam dışı (TODO'larla işaretli):**
- Piyasa Araştırma Ajanı ve Risk/Strateji Ajanı — dosyalar var, `NotImplementedError`
- RAG pipeline — arayüzler var, chunking/embedding yok
- Kimlik doğrulama, kullanıcı kaydı, gerçek borsa API entegrasyonu, deployment
- Portföy/Market/Risk detay ekranları — sadece route + boş sayfa
- Sohbet oturumu listesi/silme/arama, çoklu oturum arayüzü, mesaj düzenleme

## Sorun giderme

**CORS hatası / frontend'den API'ye istek gitmiyor:** `CORS_ORIGINS` (.env) ile
frontend'in gerçekte servis edildiği origin birebir eşleşmeli — `localhost:5173`
ile `127.0.0.1:5173` tarayıcı için **farklı origin**'dir, biri diğerini geçersiz
kılmaz. `.env.example`'daki varsayılan (`http://localhost:5173`) docker-compose
kurulumuyla uyumludur; frontend'i başka bir host/port'tan açarsanız güncelleyin.

**LLM çağrıları başarısız oluyor / `event: error` SSE'de geliyor:** Ollama'nın
host makinenizde çalıştığından ve `ollama pull qwen2.5:3b` ile modelin indirilmiş
olduğundan emin olun. Konteynerden host'a `host.docker.internal` üzerinden
ulaşılıyor; bu Linux'ta Docker Desktop dışında ekstra ayar gerektirebilir
(`docker-compose.yml`'da `extra_hosts: host.docker.internal:host-gateway` zaten var).

### Neden ayrı bir Ollama container'ı yok

Tech stack listesinde docker-compose servisleri "api + postgres + chroma +
frontend" olarak belirtilmişti; Ollama'yı konteynerize etmek ek imaj boyutu ve
model indirme karmaşıklığı getireceğinden host makinede çalıştırılması tercih
edildi. İsterseniz `docker-compose.yml`'a bir `ollama` servisi ekleyip
`OLLAMA_BASE_URL`'i buna göre güncelleyebilirsiniz.
