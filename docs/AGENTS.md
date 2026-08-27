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

1. **Plan.** LLM'e tool kataloğunu ve soruyu verip "hangi tool, hangi
   argümanla" kararını aldırır (`prompts/portfolio_agent.md` bir PLAN
   prompt'udur, anlatı şablonu değil). Katalog `client.list_tools()` ile MCP'den
   okunur, prompt'a elle yazılmaz — docstring'ler sözleşme gereği zaten bu iş
   için yazılıyor (`docs/MCP-TOOLS.md` §4), yeni bir portföy tool'u eklemek
   yalnızca `TOOLS` listesine ad eklemeyi gerektirir. Tanınmayan tool adı,
   sözlük olmayan argüman ve modelin yazdığı `user_id` elenir; plan
   üretilemezse `get_portfolio_summary`'ye düşülür. Plan başına en fazla 3 tool.
2. **Çağrı.** Plandaki tool'lar TEK MCP oturumunda eşzamanlı çağrılır.
   `user_id`'yi ajan enjekte eder — ama yalnızca `_USER_SCOPED_TOOLS`'a:
   `get_asset_price_history` portföyden bağımsızdır, imzasında `user_id`
   yoktur ve fastmcp tanımadığı argümanı doğrulama hatasıyla reddeder. Sözleşme
   `tests/test_portfolio_agent_tools.py`'de gerçek tool imzalarına karşı
   kilitli. Tek bir tool'un hatası ajanı düşürmez.
3. **Serileştirme.** `_render`, tool verisini `etiket: değer` satırlarına
   çevirir: cümle kurulmaz, yorum eklenmez. **Sayısal hiçbir değer LLM
   tarafından üretilmez**; anlatıyı orchestrator'ın `merge` adımı kurar. Uzun
   diziler anlatıya girmez — değer serisi tamamen atılır, fiyat serisi uç
   noktalara indirgenir, ham işlem listesi sembol+tür bazında toplulaştırılır
   (kronoloji korunarak: her kova ilk/son işlem gününü taşır). Grafik veriyi
   zaten API'den kendisi alıyor.
4. **Hata.** Tool'ların hepsi düşerse `success: false` döner ve hangi tool'un
   hangi sebeple düştüğü teşhis için `data` içinde kalır; bir kısmı düşerse
   "Alınamayan bilgiler" satırıyla anlatıya taşınır. İstemci tarafında oluşan
   istisnanın METNİ kullanıcıya gitmez (`_CLIENT_ERROR_MESSAGE`) — merge adımı,
   hiçbir ajan başarılı olmadığında ajan hata metnini doğrudan akıtıyor.

## Piyasa Araştırma Ajanı (`agents/market_agent.py`) — çalışıyor

Ajan iki ayrı soru tipine bakar ve **girişte dallanır**:

| Soru tipi | Nereye gider | Örnek |
|---|---|---|
| **Fiyat / kur** | `get_current_prices` | "dolar ne kadar", "gram altın kaç TL" |
| **Fiyat seyri** | `get_asset_price_history` | "dolar son bir yılda ne yaptı" |
| **Haber / bilanço / belge** | `search_market_news` (RAG) | "Aselsan haberleri", "Tüpraş 2. çeyrek bilançosu" |

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

### Canlı katman — RAG'ın üstüne eklenen, LLM'e girmeyen bloklar

RAG yalnızca **değişmeyecek arşiv bilgisi** tutar (bilanço metni, şirket
profili, referans). Güncel bilgi ayrı bir yoldan, soru anında çekilir ve
`summary_text`'in sonuna **kendi etiketli bloğu** olarak eklenir. İki blok
birbirini dışlar:

| Koşul | Tool | RAG | Blok başlığı |
|---|---|---|---|
| Şirket var **ve** güncellik isteniyor | `get_live_kap_disclosures` | çalışır, blok üstüne eklenir | `Güncel KAP Bildirimleri:` |
| Şirket yok **ve** gündem **ve** güncellik | `get_live_market_headlines` | **hiç çağrılmaz** | `Güncel Piyasa Başlıkları:` |

Karar `agents/market_query.py`'de kural tabanlı verilir. Şirket sorulduğunda
genel gündem eklenmez (sorulmayan bilgiyle cevabı seyreltir), şirket
sorulmadığında KAP'a hangi şirketi soracağımız belirsizdir.

**Gündem sorusu RAG'e hiç gitmez.** Arşivde haber yok; yine de aramaya
gidildiğinde en yakın belge dönüp kaynak listesine yazılıyordu — "son piyasa
haberleri neler" sorusunun cevabında hiç geçmeyen "Doğuş Otomotiv 2. Çeyrek
Sonuçları", sanki cevabı destekleyen bir kaynakmış gibi listeleniyordu
(ölçüldü, 24 Ağustos). Kullanılmayan bir kaynağı göstermek, kaynak
göstermenin amacını tersine çevirir.

Koşulda gündem kelimesi **tek başına yetmez**, güncellik de aranır: aksi
hâlde "piyasa değeri ne demek" gibi bir kavram sorusu da bu dala düşüp
arşive hiç bakmazdı. Canlı kaynağa ulaşılamazsa RAG yoluna düşülür — bu dal
bir kestirme, çıkmaz sokak değil.

**Bloklar LLM'den geçmez.** RAG özetiyle aynı cümlede eritilirse hangi
bilginin arşivden hangisinin canlı kaynaktan geldiği bulanıklaşır. Bu
garanti tek başına ajanda tutulamıyor: orchestrator'ın `merge_responses`
adımı tüm ajan çıktılarını ikinci bir LLM'den geçiriyor ve ilk sürümde bu
blokları düzyazıya eritiyordu (ölçüldü, 24 Ağustos). Merge prompt'una
"CANLI BLOKLARI KORU" kuralı bu yüzden eklendi.

**Dış kaynağa ulaşılamazsa blok sessizce atlanır** — RAG özeti kendi başına
geçerli bir cevaptır, canlı katman "varsa iyi" bir ektir.

Kaynaklar ve ölçümle alınan kararlar:

- **KAP** (`app/providers/kap_p.py`, `pykap` üzerinden). Resmî bir API yok;
  kütüphane KAP sayfalarını okur (AK 5.1 çekincesi). `pykap`'ın
  `get_expected_disclosure_list` fonksiyonu denendi ve **yanlış** bulundu:
  geçmiş bildirimleri değil gelecekteki dosyalama takvimini döndürüyor.
  Doğrusu `get_historical_disclosure_list`.
- **BloombergHT** (`app/providers/bloomberg_ht_p.py`, httpx + lxml). Yalnızca
  **genel gündem** verir, şirket bazlı haber vermez: bir hissenin kendi
  sayfasındaki "İlgili Haberler" bloğu genel `/borsa` sayfasınınkiyle birebir
  aynı çıktı, şirket bazlı haber ancak `robots.txt`'nin yasakladığı site içi
  aramadan gelir. `sitemap_google_news.xml` de kullanılmadı — içeriği iki ay
  eskiydi. Maddelerin ayrı bağlantısı yok, kaynak olarak sayfanın kendisi
  verilir; olmayan bir permalink üretilmez. Sonuç 5 dakika önbellekte tutulur.

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

## Web Araştırma Ajanı (`agents/web_research_agent.py`) — çalışıyor

Genel finans kavramlarını açıklar: "lot ne demek", "borsa saat kaçta kapanır",
"takas kaç gün sürer", "portföy kârı nasıl hesaplanır".

**Adı "web araştırması" ama bugün web'e çıkmıyor** — cevap dil modelinin kendi
bilgisinden gelir. İsim ileride eklenecek dış arama yolunu şimdiden
işaretliyor; kullanılmayan yol ölü kod olacağı için bugün yazılmadı.

Sistemdeki **tek LLM-bilgisi ajanı**: diğerlerinde sayılar deterministik koddan
gelir ve LLM yalnızca anlatır, burada bilginin kendisi modelden geliyor.
Sınırlar bu yüzden `prompts/web_research_agent.md`'de sert — portföye atıf yok,
güncel fiyat/kur/faiz/endeks değeri yok (o alan Piyasa Ajanı'nın),
kişiselleştirilmiş tavsiye yok, zamanla değişen olgularda (seans saati, takas
süresi, komisyon) resmî kaynağa yönlendirme zorunlu.

### RAG ile sınır — ölçüme dayalı

**Kavram ve prosedür sorularının tamamı bu ajana gelir**, arşivde belgesi olsa
bile. Ayrım arşiv üyeliğine değil sorunun türüne bağlı (`detect_intent`,
"KAVRAM mı VERİ mi"): kavramın KENDİSİ mi soruluyor, yoksa belirli bir
şirkete/döneme ait VERİ mi.

| soru | ajan |
|---|---|
| "temettü nedir" · "TFRS 16 nedir" · "F/K oranı nasıl hesaplanır" | web_research |
| "takas kaç gün sürer" · "borsa saat kaçta kapanır" · "lot ne demek" | web_research |
| "Akbank'ın 2026 temettüsü ne kadar" · "Aselsan haberleri" | market |
| "ne kadar temettü aldım" | portfolio |

Önce denenen ayrım — "arşivde belgesi varsa MARKET" — iki yerden birden
kırıldı:

1. **Sınıflandırıcı arşivde ne olduğunu bilemez.** Kararı tahmine bağlıyordu.
2. **Belgenin var olması, getirilebileceği anlamına gelmiyor.**
   `rag/retriever.py` bir sonucu ancak sorguyla paylaşılan kelimelerden en az
   biri JENERİK DEĞİLSE kabul ediyor. `_GENERIC_FINANCE_TERMS` içinde
   `temettu`, `halka`, `arz` var — 31 şirket profilinin tamamında geçtikleri
   için oraya konmak zorunda kaldılar (yoksa uydurma şirket sorguları gerçek
   şirket verisi döndürüyordu). Sonuç: "temettü nedir",
   `REFERANS_kurumsal-olay-terimleri.md` içinde `## Temettü (Kâr Payı)`
   başlığı AYNEN dururken bile *"Veritabanımızda bu sorguyla ilgili
   doğrulanmış bir bilgi bulunamadı"* dönüyordu (ölçüldü, 27 Ağustos).

Kısır döngü: bir terim ne kadar yaygınsa o kadar çok belgede geçer, o kadar
jenerik işaretlenir, tanımı o kadar bulunamaz. **En çok sorulan kavramlar
yapısal olarak en çok başarısız olanlar** — bu yüzden istisna bırakılmadı.

**Bedeli:** `REFERANS_*.md` belgeleri tanım sorularında artık kullanılmıyor,
dolayısıyla o cevaplar `Kaynaklar:` listesi taşımıyor. Prompt kuralı 5 bunu
kısmen karşılıyor (değişebilen olgularda ve düzenleme/standart sorularında
resmî kaynağa — KGK, SPK, BDDK — yönlendirme zorunlu). Belgeleri ileride bu
ajana bağlamak ayrı bir iş.

Yönlendirmenin gerçek modelle doğrulanması: `scripts/intent_smoke.py`.

### Ev kuralları

Prompt, bu uygulamanın kendi hesap tanımlarını taşıyor: kâr tabanı = dışarıdan
konan net sermaye, dönem getirisi = TWR, kıyaslamada t0 miktarları sabit,
ağırlık paydası nakit dahil. Sebebi, "portföy kârı nasıl hesaplanır" sorusuna
ders kitabı cevabı vermenin açıklamayla ekrandaki rakamı birbirine
yalanlatması. Tanımların kaynağı `docs/API.md`; oradaki kural değişirse prompt
da güncellenmeli.

### Kısıtlı konular

`scope.yaml` → `kisitli_konular` etiketleri (bugün yalnızca vergi) sorguda
geçerse prompt'a ek kural bloğu eklenir: sayı verme, kişisel hesap yapma, koşul
dili kullan, mali müşavire yönlendir. Kurallar da yönlendirme metni de YAML'dan
okunur, ajanda yeniden yazılmaz.

**Bilinen sınır.** Ajanın metni kullanıcıya doğrudan gitmiyor; `merge` adımında
ikinci bir LLM turundan geçiyor. Merge'ün "elenemez" listesinde (ALINAMAYAN
BİLGİLER, `Kaynaklar:`, canlı bloklar) vergi yönlendirmesi ve kapanış uyarısı
YOK — düşebilirler. Düzeltme `merge_responses`'ı değiştirmeyi gerektiriyor
(dört ajanı birden etkiler) ve ayrı iş olarak duruyor. Ajan ayrıca sohbet
geçmişini okumuyor: takip soruları ("peki ne zaman verilir") bağlamsız gidiyor.

## Orchestrator (`agents/orchestrator.py`) — LangGraph

```
                ┌─> portfolio_agent ────┐
                ├─> market_agent ───────┤
detect_intent ──┼─> risk_agent ─────────┼─> merge → END
                ├─> web_research_agent ─┘
                └─> handle_out_of_scope → END
```

- `detect_intent`: önce kural tabanlı kapsam kontrolü (`scope_checker`), sonra
  LLM ile sınıflandırma. `PORTFOLIO`, `MARKET`, `RISK`, `WEB_RESEARCH`
  etiketlerinden **bir veya birkaçı** seçilebilir; `intent` alanı bunları `"+"` ile birleştirir
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
5. Bu belgeye ajanın bölümünü ve yukarıdaki diyagrama node'unu ekle. Yeni ajan
   kapsam kurallarını değiştiriyorsa (`scope.yaml`) neyin neden değiştiğini de
   yaz — kural motoru dört ajanın ortak kapısı.
