# Ekip Özeti — Proje Artık Canlıda

**Tarih:** 12 Ağustos 2026 · **Hazırlayan:** Sude

Dün projeyi sunucuya aldık. Bu doküman ne değiştiğini ve bundan sonra nasıl
çalışacağımızı anlatıyor. Okuması 5 dakika.

---

## 1. Artık iki adresimiz var

| Ortam | Adres | Kim kullanır |
|---|---|---|
| **Test** | https://test.34.159.243.0.nip.io | İş analistleri, ekip |
| **Canlı** | https://app.34.159.243.0.nip.io | Demo, sunum |

Test ortamı şifre korumalı:

```
kullanıcı: analist
şifre:     analistvira
```

Canlı ortam şifresiz — demo günü jüriye gösterilecek olan burası.

İkisi **tamamen ayrı veritabanları** kullanıyor. Test ortamında veriyle
oynamak canlı ortamı etkilemez.

> Adresler uzun görünüyor çünkü `nip.io` kullanıyoruz — kayıt gerektirmeyen
> ücretsiz bir DNS servisi. Demo öncesi gerçek bir alan adına geçeceğiz,
> sistemin geri kalanı aynı kalacak.

---

## 2. Çalışma şeklimiz değişti

Artık `main` ve `test` branch'lerine **doğrudan push yapılamıyor**. Her
değişiklik PR'dan geçmek zorunda.

### Günlük akış

```bash
git checkout test && git pull
git checkout -b feature/yaptigin-is
# ... çalış, commit at ...
git push -u origin feature/yaptigin-is
```

Sonra GitHub'da **`test`'e** PR aç. Otomatik testler koşar (2-3 dakika).
Yeşilse merge et — test ortamı **kendiliğinden güncellenir**, kimsenin
sunucuya girmesine gerek yok.

### Canlıya çıkarma

1. Test ortamında değişikliği doğrula
2. WhatsApp grubundan analistlere haber ver
3. Onay gelince `test` → `main` PR'ı aç
4. Bir ekip arkadaşı onaylasın
5. Merge et → canlı ortam kendiliğinden güncellenir

`main`'e **yalnızca `test` branch'inden** PR açılabilir. Feature dalından
doğrudan canlıya çıkmak engelleniyor — hiçbir şey test ortamında görülmeden
demoya gitmesin diye.

### Analistlere yazarken

Şu üç bilgiyi ver, yoksa neye bakacaklarını bilemezler:

> **Ne değişti:** Risk ekranına yeniden dengeleme önerisi eklendi
> **Nereye bakılacak:** test adresine gir → Risk sekmesi
> **Neyi doğrulaman lazım:** Öneri kartı görünüyor mu, sayılar mantıklı mı

---

## 3. Dikkat: lint artık merge'ü engelliyor

`ruff`, `black` ve `eslint` otomatik testlerin parçası. Biçimlendirilmemiş kod
PR'ı kırmızıya düşürür ve merge edemezsiniz.

Push etmeden önce bir kez çalıştırın, zaman kazandırır:

```bash
docker run --rm -v "$PWD":/src -w /src python:3.11-slim \
  bash -c "pip install -q ruff black && ruff check . --fix && black ."

cd frontend && npx eslint . --ext ts,tsx --fix
```

Kural seti `pyproject.toml` içinde sabitlendi — herkeste ve CI'da aynı davranır.

---

## 4. Yeni eklenen: Giriş sayfası

Ana sayfa artık bir tanıtım sayfası: proje açıklaması, dört ajanın kartları,
nasıl çalıştığını anlatan adımlar ve yatırım tavsiyesi uyarısı.

Dashboard `/dashboard` adresine taşındı.

---

## 5. Kullandığımız teknolojiler

### Uygulama

| Katman | Teknoloji | Ne işe yarıyor |
|---|---|---|
| Backend | **Python 3.11 + FastAPI** | REST API, otomatik OpenAPI dokümanı |
| Şema/doğrulama | **Pydantic v2** | Değiştirilemez (frozen) veri modelleri |
| Yapılandırma | **pydantic-settings** | Tüm ayarlar `.env`'den, kodda sabit yok |
| ORM | **SQLAlchemy 2.x** | Tiplenmiş modeller (`Mapped[...]`) |
| Migration | **Alembic** | Şema değişikliklerinin sürüm kontrolü |
| Veritabanı | **PostgreSQL 16** | Kullanıcı, portföy, işlem, sohbet verileri |
| Sürücü | **psycopg 3** | Async destekli yeni nesil PostgreSQL sürücüsü |
| Akış | **sse-starlette** | Cevabın token token akması (SSE) |
| HTTP istemci | **httpx** | Ollama'ya asenkron bağlantı |
| Ajan çatısı | **LangGraph** | Orchestrator'ın graf tabanlı akışı |
| Araç protokolü | **fastmcp** | Ajanların veriye MCP üzerinden erişimi |
| LLM | **Ollama + qwen2.5:3b** | Yerel çalışan dil modeli |
| Vektör DB | **Chroma** | RAG için (henüz boş) |
| Sahte veri | **Faker** | 50 kullanıcı, 12 aylık fiyat geçmişi |

### Arayüz

**React 18 + TypeScript + Vite** · **TanStack Query** (veri çekme ve önbellek) ·
**Recharts** (grafikler) · **Tailwind CSS** · **React Router**

### Altyapı ve süreç

| Ne | Teknoloji |
|---|---|
| Sunucu | Google Cloud e2-standard-4 (4 vCPU / 16 GB), Frankfurt |
| Konteyner | Docker + Docker Compose |
| Ters proxy / HTTPS | Caddy (Let's Encrypt sertifikaları otomatik) |
| CI | GitHub Actions — ruff, black, pytest, eslint, build |
| CD | GitHub Actions — SSH ile otomatik deploy |
| Test | pytest (SQLite ile), vitest |

Maliyet: **0 TL.** Google Cloud'un $300 öğrenci kredisiyle karşılanıyor.

---

## 6. Mimarideki iki önemli karar

**Ajanlar veritabanına doğrudan erişmiyor.** Her veri MCP araçlarından geçiyor.
Bu sayede yetkilendirme, loglama ve doğrulama tek noktada toplanabiliyor.
Sayısal hiçbir değer modelin uydurmasına bırakılmıyor.

**LLM sağlayıcısı soyutlanmış.** `app/core/llm_client.py` içinde bir arayüz var;
Ollama, OpenAI ve Azure implementasyonları onu uyguluyor. `.env`'de tek satır
değiştirerek sağlayıcı değiştirilebiliyor, kod hiç değişmiyor.

---

## 7. Sırada ne var

- RAG pipeline (`rag/ingest.py`, `rag/retriever.py`) — Piyasa Ajanı buna bağımlı
- Piyasa Araştırma Ajanı ve Risk/Strateji Ajanı
- Portföy, Piyasa, Risk ekranları
- Kullanıcı seçim ekranı (şu an UUID elle yapıştırılıyor)
- Model kararı — bkz. `docs/LLM-SECENEKLERI.md`

Detaylı kurulum ve sorun giderme: `docs/DEPLOYMENT.md`
