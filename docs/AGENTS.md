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

Ajan iki ayrı soru tipine bakar ve **girişte dallanır**:

| Soru tipi | Nereye gider | Örnek |
|---|---|---|
| **Fiyat / kur** | `get_current_prices` | "dolar ne kadar", "gram altın kaç TL" |
| **Fiyat seyri** | `get_asset_price_history` | "dolar son bir yılda ne yaptı" |
| **Haber / bilanço / kavram** | `search_market_news` (RAG) | "Aselsan haberleri", "net faiz marjı ne demek" |

Dallanma `agents/price_query.py` ile **kural tabanlı** yapılır, LLM
kullanılmaz: soru tipi ("ne kadar", "kaç TL") ve varlık adı sonlu ve iyi
tanımlı bir küme. İkinci bir LLM planlayıcısı hem yanıta gecikme ekler hem de
sohbetin en sık sorulan sorusunu modelin gününe bağlardı.

**Neden bu dal var:** kur ve fiyat dokümanlarda değil `price_history`
tablosunda yaşıyor. Dal olmadan "dolar ne kadar?" belge aramasına düşüyor ve
"veritabanımızda bu sorguyla ilgili doğrulanmış bir bilgi bulunamadı"
dönüyordu — elde güncel kur dururken (ölçüldü, 23 Ağustos test turu).

**Fiyat yolunda LLM devrede değil:** sayılar tool'dan geldiği gibi geçer,
cümleyi orchestrator'ın merge adımı kurar. Fiyatın tarihi ve kaynağı her
satırda yazılır — fiyat "bugünün" fiyatı olmak zorunda değil (piyasa hafta
sonu kapalı) ve tarihi söylemeden vermek olmayan bir tazelik iddia etmek
olurdu. Beklenenden eski fiyat gizlenmez, eskiliği söylenir.

**Haber yolu** (`search_market_news`) saf DB tabanlı RAG'dır (LLM yok,
internetten canlı veri çekmez). Sorguyla alakalı kayıt yoksa tool
`NOT_FOUND` döner, ajan bunu diğer tool hatalarıyla aynı yoldan
(`AgentResponse.error`) taşır. Bu yolda üç adım uygulanır:

1. **Deterministik filtre** — `agents/market_query.py` sorgudan şirket kodunu
   (`data/company_mappings.json`) ve dönemi (`2026-Q2`) çıkarır, tool'a
   `sirket`/`donem` olarak geçirir. Arama uzayı vektör benzerliği
   hesaplanmadan ÖNCE daralır. Kural tabanlıdır, LLM kullanmaz. Yıl açıkça
   yazılmamışsa dönem üretilmez — yanlış filtre, doğru doküman veritabanında
   dururken "bulunamadı" dedirtir.
2. **Yedek deneme** — filtreli arama boş dönerse bir kez de filtresiz denenir.
   Filtre bir doğruluk aracıdır, cevabı büsbütün engellememeli.
3. **Etiketli özet** — her parça `[n] Başlık (Kaynak, tarih)` başlığıyla LLM'e
   verilir, LLM yalnızca bu metinden Türkçe özet yazar (sayı üretmesi
   `agents/prompts/market_agent.md`'de yasaklı). Kaynak listesi LLM'e
   bırakılmaz, metadata'dan üretilip akışın sonuna eklenir.

Etiketleme kritik: parçalar eskiden etiketsiz birleştiriliyordu ve model iki
ayrı şirketin rakamlarını tek cümlede harmanlayabiliyordu.

## Risk Ajanı

`agents/risk_agent.py`: `get_risk_assessment` tool'unu çağırır, dönen
değerlendirmeyi `prompts/risk_agent.md` ile Türkçeleştirir. Portföy Ajanı'yla
aynı kalıp — **sayısal hiçbir değer LLM tarafından üretilmez**; volatilite,
VaR, Sharpe ve senaryoların tamamı `app/services/risk_service.py` hesabıdır.

İki tasarım kararı:

- **Senaryolar isteğe bağlı.** Tool'da `include_scenarios` varsayılan kapalı
  (ek hesap maliyeti). Ajan yalnızca sorguda "dengele / azalt / öneri /
  strateji / ne yapmalı" köklerinden biri geçtiğinde açar (`_wants_scenarios`).
- **Değerlendirme küçültülerek verilir** (`_compact`). Ham `RiskAssessment`
  korelasyon matrisi, kategori metrikleri ve senaryo başına varlık kırılımı
  taşır; küçük bir modele tamamını vermek hem yavaş hem dikkat dağıtıcı.
  `None` alanlar **korunur** — risk hesaplanamadığında model bunu görüp
  "hesaplanamadı" demeli (CLAUDE.md §4 uydurmama).

### `profil_konumu` — bandın altında kalmak da bir uyumsuzluktur

`risk_service` yalnızca **üst** sınırı kontrol ediyor:

```python
is_within_profile = volatility <= band_upper   # risk_service.py:1252
```

Bandın **altında** kalmak da "içinde" sayılıyor. Sonuç: Agresif profilli,
%3,5 volatiliteli bir kullanıcıya "profilinizin içindesiniz" deniyordu.
Ölçüldü: 50 kullanıcının 32'si bu durumda.

`_compact` bu boşluğu `profil_konumu` alanıyla kapatıyor —
`bandin_altinda` / `band_icinde` / `bandin_ustunde`. Üst sınır kararı
**servisten alınır**, ajan yeniden hesaplamaz; iki katmanın çelişmesi mümkün
olmasın diye. Karşılaştırma kodda yapılır, prompt'a bırakılmaz.

`bandin_altinda` durumunda ajan yalnızca **tespit** yapar ("beyan ettiğiniz
risk tercihinin altında kalıyor"); risk artırıcı yönlendirme prompt kural
9'da açıkça yasaklı ve o durum için senaryo üretilmez. Yukarı yönlü öneri
motorun kendisini değiştirmeyi gerektirir (`_target_volatility` hep üst
sınırı hedefliyor, aksiyonlar riskli→savunma yönünde taşıyor) ve ayrıca bir
ürün kararıdır — analist onayı bekliyor.

## Orchestrator (`agents/orchestrator.py`) — LangGraph

```
                ┌─> portfolio_agent ─┐
detect_intent ──┼─> market_agent ────┼─> merge → END
                ├─> risk_agent ──────┘
                └─> handle_out_of_scope → END
```

- `detect_intent`: önce kural tabanlı kapsam kontrolü (`scope_checker`), sonra
  LLM ile sınıflandırma. `PORTFOLIO`, `MARKET`, `RISK` etiketlerinden **bir
  veya birkaçı** seçilebilir; `intent` alanı bunları `"+"` ile birleştirir
  (`"portfolio+risk"`). Eski tek kelimelik `BOTH` geriye dönük tanınır.
  Etiket alanı orchestrator dışına çıkmaz.
- **`RISK` etiketi "risk" kelimesi geçmeyen sorularda da seçilir**
  ("portföyümde çok fazla hisse mi var", "nasıl dengelemeliyim"). Prompt bunu
  örneklerle zorunlu tutuyor: kullanıcı riski sormak için "risk" demek zorunda
  değil.
- **Tanınmayan etiket portföye düşmez.** Eskiden `_route_after_intent`
  koşulsuz `["portfolio_agent"]` dönüyordu; risk soruları buraya düşüp
  sessizce portföy özetiyle cevaplanıyordu. Artık anlaşılmayan soru açıkça
  sorulur.
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
- `merge`: başarılı ajan yanıtlarını LLM ile tek metinde birleştirir.
  Hiçbiri başarılı değilse **ajanların kendi hata mesajları** gösterilir —
  bunlar kullanıcıya gösterilmek üzere yazılmıştır (`tools/_base.py`
  `DEFAULT_MESSAGES`) ve durumları ayırt eder: "İstenen kayıt bulunamadı."
  ile "Veri kaynağına şu anda ulaşılamıyor." aynı şey değildir. Eskiden ikisi
  de tek bir "sistemlerimize ulaşılamıyor" metnine düşüyor, RAG'de doküman
  bulunamaması ayakta olan sistemi çökmüş gibi gösteriyordu.
  `stream` istisna atmadan hiç parça üretmezse ham metinlere düşülür —
  aksi halde arayüzde boş balon kalıyordu.

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
