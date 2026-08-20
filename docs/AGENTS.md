# Ajan Mimarisi

> Ajanların veriye eriştiği tek yol MCP tool'larıdır. Tool'ların dönüş zarfı,
> hata kodları, docstring biçimi ve test şablonu için: **[`docs/MCP-TOOLS.md`](MCP-TOOLS.md)**.
> Ajan yazarken bilinmesi gereken özet: tool başarılıysa `data` **her zaman**
> vardır; başarısızsa `error.code` sabit kümeden gelir (`NOT_FOUND`,
> `INSUFFICIENT_DATA`, `INVALID_ARGUMENT`, `PROVIDER_UNAVAILABLE`, `TIMEOUT`,
> `INTERNAL_ERROR`) ve `error.message` kullanıcıya doğrudan gösterilebilir.
> Tool'lar istisna sızdırmaz — `call_mcp_tool` etrafına `try/except` gerekmez.

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

## Piyasa Araştırma Ajanı (`agents/market_agent.py`) — çalışıyor

`search_market_news` MCP tool'unu çağırır. Tool saf DB tabanlı RAG'dır (LLM
yok, internetten canlı veri çekmez); ajan da üstüne LLM'e gitmez, tool'dan
gelen doküman parçalarını olduğu gibi `summary_text`'e taşır. Sorguyla
alakalı kayıt yoksa tool `NOT_FOUND` döner, ajan bunu diğer tool
hatalarıyla aynı yoldan (`AgentResponse.error`) taşır.

## Risk/Strateji Ajanı (`agents/risk_agent.py`) — çalışıyor

`get_risk_assessment` MCP tool'unu çağırır, dönen değerlendirmeyi
`prompts/risk_agent.md` ile Türkçeye döker. Portföy Ajanı'yla aynı kalıp:
volatilite, VaR, Sharpe ve senaryoların tamamı `app/services/risk_service.py`
tarafından hesaplanır, LLM yalnızca özetler.

İki ayrıntı:

- **Senaryolar isteğe bağlı.** Tool'da `include_scenarios` varsayılan olarak
  kapalı (ek hesap maliyeti). Ajan, sorguda "dengele", "azalt", "öneri",
  "strateji" gibi bir kök geçiyorsa açar (`_wants_scenarios`).
- **Değerlendirme küçültülerek verilir** (`_compact`). Ham `RiskAssessment`
  korelasyon matrisi ve senaryo başına varlık kırılımı taşıyor; küçük bir
  modele tamamını vermek hem yavaş hem dikkat dağıtıcı. `None` alanlar
  KORUNUR — risk hesaplanamadığında model bunu görüp "hesaplanamadı" demeli
  (CLAUDE.md §4 uydurmama ilkesi).

## Orchestrator (`agents/orchestrator.py`) — LangGraph

```
detect_intent ─┬─> handle_out_of_scope ─────────────> END
               ├─> portfolio_agent ─┐
               ├─> market_agent ────┼─> merge ─────> END
               └─> risk_agent ──────┘
```

- `detect_intent` iki aşamalı: önce kural tabanlı kapsam filtresi (işlem
  talepleri ve finans dışı sohbet, LLM'e hiç gitmeden reddedilir), sonra LLM
  ile niyet sınıflandırma. Sınıflandırıcı `PORTFOLIO`, `MARKET`, `RISK`
  etiketlerinden **bir veya birkaçını** döndürebilir; seçilen ajanlar sırayla
  çalışır. Etiket tanınmazsa ya da LLM düşerse portföy ajanına düşülür.
- **Kapsam filtresi kelime bazlı eşleşir, alt dizi değil.** Alt dizi araması
  "portföy an**al**izi", "**al**tın ne durumda", "**hava**cılık hisseleri"
  gibi meşru soruları işlem talebi sayıp reddediyordu (üretimde gözlendi,
  bkz. `tests/test_orchestrator_routing.py`).
- Ajan node'ları `writer: StreamWriter` parametresi alır —
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
- `merge` üç yoldan biriyle çalışır ve **her yolda kullanıcıya en az bir delta
  akıtır**:
  1. Kullanılabilir metin yoksa tool'ların hata mesajları gösterilir (bunlar
     kullanıcıya gösterilmek üzere yazılmıştır, bkz. `tools/_base.py`
     `DEFAULT_MESSAGES`); hiç yanıt yoksa genel sistem mesajı.
  2. Tek ajan çalıştıysa ve eksik bilgi yoksa metin **doğrudan** akıtılır —
     ikinci bir LLM turu bilgi eklemeden gecikme (≤5 sn hedefi) ve bir kırılma
     noktası ekler.
  3. Birden fazla kaynak ya da kısmi başarı varsa LLM ile tek metne indirilir;
     LLM boş dönerse ya da düşerse ham metinlere düşülür.

  Boş yanıt koruması şuradan geliyor: merge LLM'i istisna atmadan boş yanıt
  döndürdüğünde ne token ne hata üretiliyordu, arayüzde boş balon kalıyordu
  (üretimde gözlendi).
- Sorumluluk reddi (`DISCLAIMER`) her yolda **kod tarafından** garanti edilir;
  LLM'in eklemesine güvenilmez (CLAUDE.md §4). Metin zaten taşıyorsa
  ikilenmez.

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
