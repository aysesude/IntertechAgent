# API Sözleşmesi

Şemaların tanımlı olduğu yer: `backend/app/schemas/`. Frontend tipleri
(`frontend/src/types/`) bunlarla birebir eşleşmelidir.

## REST

### `GET /api/portfolio/{user_id}`

```json
{
  "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "as_of": "2026-08-10",
  "total_value": 1497558.96,
  "total_cost_basis": 1570215.80,
  "total_gain_loss": { "amount": -72656.84, "percent": -4.63 },
  "allocation": [
    { "asset_class": "stock", "value": 167808.53, "percent": 11.21 },
    { "asset_class": "precious_metal", "value": 555795.65, "percent": 37.11 },
    { "asset_class": "currency", "value": 471330.61, "percent": 31.47 },
    { "asset_class": "bond", "value": 302624.17, "percent": 20.21 }
  ],
  "holdings_count": 14
}
```

404 → `{"detail": "Portfolio not found for user_id ..."}`

Not: sayısal alanlar hesaplamada `Decimal` ile tutulur, JSON'a `float` olarak
serialize edilir (bkz. `app/schemas/portfolio.py`'deki `Money` tipi) — string
değil, frontend doğrudan `number` olarak tüketir.

### `POST /api/chat` (SSE, `text/event-stream`)

İstek:
```json
{ "user_id": "3fa85f64-...", "session_id": null, "message": "Portföyümün durumu nasıl?" }
```
`session_id: null` ise yeni bir `ChatSession` açılır; verilirse mevcut oturuma
devam edilir (yoksa `404`). Kullanıcı mesajı, ajanlar çalışmadan **önce** DB'ye
yazılır.

Yanıt akışı:
```
event: session
data: {"session_id": "b1e2..."}

event: token
data: {"delta": "Portföyünüzün"}

event: done
data: {"agent": "portfolio_agent", "final_answer": "...", "data": { ...PortfolioSummary... }}

event: error
data: {"message": "..."}   # sadece hata durumunda, done yerine
```
Asistan mesajı stream tamamlanınca tek parça DB'ye yazılır (`status: complete`).
İstemci bağlantıyı yarıda keserse, o ana kadar biriken metin `status: incomplete`
ile kaydedilir.

### `GET /api/chat/sessions/{session_id}/messages`

Oturumdaki tüm mesajları kronolojik sırada döner:
```json
[
  {
    "id": "8670e68a-...",
    "role": "user",
    "content": "Portföyümün durumu nasıl?",
    "agent_name": null,
    "meta": null,
    "status": "complete",
    "created_at": "2026-08-10T13:49:13"
  },
  {
    "id": "4814d25f-...",
    "role": "assistant",
    "content": "...",
    "agent_name": "portfolio_agent",
    "meta": { "data": { ...PortfolioSummary... } },
    "status": "complete",
    "created_at": "2026-08-10T13:49:15"
  }
]
```
404 → `{"detail": "Chat session not found for session_id ..."}`

### İskelet route'lar

- `GET /api/market/news` → `501` + `{"detail": "TODO: ..."}`

## MCP Tool'ları

MCP Server `http://mcp_server:8100/mcp` üzerinde dinler (docker ağı içinde).

### `get_portfolio_summary` (çalışıyor)

```
Girdi:  { "user_id": "<UUID>" }
Çıktı (başarı): { "success": true, "data": { ...PortfolioSummary... } }
Çıktı (hata):   { "success": false, "error": { "code": "PORTFOLIO_NOT_FOUND", "message": "..." } }
```
`user_id` geçersiz UUID ise tool çağrılmadan otomatik `ValidationError` fırlar
(pydantic, tip anotasyonundan üretilen JSON şemasıyla).

### `search_market_news` (çalışıyor)

```
Girdi:  { "query": "...", "top_k": 5 }
Çıktı (başarı): { "success": true, "data": { "found": bool, "message": str | null,
                  "results": [{ "content": "...", "metadata": {...}, "distance": 0.0 }, ...] } }
Çıktı (hata):   { "success": false, "error": { "code": "RAG_ERROR", "message": "..." } }
```
Saf DB tabanlı arama: LLM yanıt üretmez, internetten canlı veri çekmez.
`data/documents/` altındaki dokümanlar `python -m rag.ingest` ile Chroma'ya
yüklenir; sorguya `rag_distance_threshold` (bkz. `app/core/config.py`) altında
kalan bir sonuç yoksa `found: false` ve bulunamadı mesajı döner.

### İskelet tool'lar (`NotImplementedError`)

- `get_risk_assessment(user_id: str)` — `mcp_server/tools/risk_tools.py`
