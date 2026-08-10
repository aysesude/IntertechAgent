# Ajan Mimarisi

## Ortak sözleşme (`agents/base.py`)

```python
class AgentRequest(BaseModel):
    user_id: str
    session_id: str
    query: str
    context: dict[str, Any] = {}   # ör. son N mesajlık sohbet geçmişi

class AgentResponse(BaseModel):
    agent_name: str
    success: bool
    summary_text: str
    data: dict[str, Any] | None    # tool'dan gelen ham yapısal veri
    error: str | None
```

`BaseAgent`:
- `call_mcp_tool(tool_name, arguments)` — MCP Server'a **ağ üzerinden**
  (`fastmcp.Client`) bağlanır. Ajanlar servis katmanını veya DB'yi asla
  doğrudan import etmez; tek veri erişim yolu budur.
- `execute(request, *, on_token=None)` — abstract. `on_token` verilirse
  (SSE stream'i için), LLM yanıtı üretilirken her parça geldikçe çağrılır.

## Portföy Ajanı (`agents/portfolio_agent.py`) — çalışıyor

1. `get_portfolio_summary` MCP tool'unu çağırır.
2. Başarısızsa (`success: false`) hatayı `AgentResponse.error`'a taşır, LLM'e
   hiç gitmez.
3. Başarılıysa, tool'dan gelen JSON'u `agents/prompts/portfolio_agent.md`
   şablonuna gömer ve `app.core.llm_client` üzerinden (Ollama) stream eder.
   **Sayısal hiçbir değer LLM tarafından üretilmez** — LLM sadece tool'dan
   gelen veriyi Türkçe anlatıya döker.

## Market / Risk Ajanları — iskelet

`agents/market_agent.py`, `agents/risk_agent.py`: `BaseAgent`'i implement
eder, `execute()` gövdesi `NotImplementedError`. Karşılık gelen MCP tool'ları
(`search_market_news`, `get_risk_assessment`) de aynı şekilde iskelet.

Risk eşikleri (volatilite, yoğunlaşma limitleri vb.) tanımları kullanıcıyla
netleştirilmeden `app/core/config.py`'ye eklenmedi — bkz. oradaki TODO notu.

## Orchestrator (`agents/orchestrator.py`) — LangGraph

```
detect_intent → portfolio_agent → merge
```

- `detect_intent`: şu an niyet sabit `"portfolio"` (tek ajan bağlı olduğu
  için gerçek niyet tespiti henüz yok).
- `portfolio_agent` node'u `writer: StreamWriter` parametresi alır —
  LangGraph tarafından otomatik enjekte edilir, `stream_mode="custom"`
  kullanılmadığında no-op'tur. Bu sayede **tek bir graf** hem tek seferlik
  (`run_orchestrator`, testler için) hem stream'li (`stream_orchestrator`,
  SSE endpoint'i için) çağrıyı destekler — kod tekrarı yok.
- `agent_responses` state alanı `Annotated[list[AgentResponse], operator.add]`
  ile tanımlı: Market/Risk ajanları paralel node olarak eklendiğinde
  sonuçlarını aynı listeye biriktirebilecekler, state şeması değişmeyecek.
- `history` state alanı: son N mesajlık sohbet geçmişini taşır
  (`AgentRequest.context["recent_messages"]`'a geçiyor). **PortfolioAgent şu
  an bunu prompt'una dahil etmiyor** (tek turluk çalışıyor) — çok turlu bağlam
  gereken ajanlar için altyapı hazır tutuluyor.
- `merge`: başarılı ajan yanıtlarının `summary_text`'lerini birleştirir; hiçbiri
  başarılı değilse ilk hatayı `final_answer` olarak döner.

## Yeni bir ajan eklerken

1. `agents/<isim>_agent.py`: `BaseAgent`'i implement et, MCP tool'unu
   `call_mcp_tool` üzerinden çağır.
2. Gerekiyorsa `mcp_server/tools/<isim>_tools.py`'de yeni bir tool tanımla,
   `mcp_server/server.py`'de `register()` ile bağla.
3. `agents/orchestrator.py`'de yeni bir node ekle, `agent_responses`'a
   sonucunu yazsın (reducer zaten hazır).
4. `detect_intent`'i güncelleyip hangi durumda hangi node'ların çalışacağına
   karar ver (paralel dağıtım için `graph.add_edge` ile birden fazla node'u
   aynı önceki node'dan bağlayabilirsin).
