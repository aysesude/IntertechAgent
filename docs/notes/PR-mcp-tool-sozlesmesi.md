> **Geçici çalışma notu — 18 Ağustos 2026.** Bu dosya `feature/mcp-tool-sozlesmesi` PR'ının açıklama metnidir; kayıt olsun diye repo'da duruyor. Sözleşmenin **kalıcı** ve güncel hâli [`docs/MCP-TOOLS.md`](../MCP-TOOLS.md)'dedir — çelişki olursa o geçerlidir.

# MCP tool sözleşmesi: ortak zarf, hata taksonomisi, zaman aşımı, log

**Dal:** `feature/mcp-tool-sozlesmesi` → `test` · **İzlenebilirlik:** US-22 (MCP
altyapısı), AK 5.5 / 5.10 (uydurmama, belirsizlikte bilgilendirme), NFR "zarif
düşüş" · **Sözleşme:** `docs/MCP-TOOLS.md`

## Neden

Bu hafta MCP tool sayısı 2'den ~10'a çıkıyor ve tool'lar farklı kişiler
tarafından paralel yazılacak. Ortak bir sözleşme yazılı olmadan dört farklı hata
biçimi, dört farklı log alışkanlığı ve ajan tarafında dört ayrı özel durum
çıkar. Bu PR yeni bir yetenek eklemiyor; **diğer sekiz tool'un üzerine oturacağı
zemini** kuruyor ve zemini tek bir örnek (`get_portfolio_summary`) üzerinde
gösteriyor.

Gerekçenin somut kanıtı: `risk-agent-yagiz` dalında yazılan üçüncü tool zaten
dördüncü bir hata kodu (`RISK_TARGET_NOT_FOUND`) getirmiş durumda.

## Ne değişti

**Yeni: `mcp_server/tools/_base.py`** — sözleşmenin uygulaması.

- `ToolErrorCode`: 6 kodluk sabit taksonomi (`NOT_FOUND`, `INSUFFICIENT_DATA`,
  `INVALID_ARGUMENT`, `PROVIDER_UNAVAILABLE`, `TIMEOUT`, `INTERNAL_ERROR`).
  Alan adına özel kod yazılmıyor.
- `DEFAULT_MESSAGES`: kullanıcıya gösterilen Türkçe metinler tek yerde.
- `@tool_handler(...)`: zarf + `AppError.code` → tool kodu eşlemesi + zaman
  aşımı + tek satır log. Senkron gövdeyi worker thread'e alır, async gövdeyi
  doğrudan `await` eder — **tool yazarı bu seçimi düşünmek zorunda kalmıyor.**
- `ToolFailure(code, message, detail=...)`: beklenen başarısızlığı bildirme
  yolu; `detail` **yalnızca loga** gider, zarfta `detail` alanı yok.
- `ToolPayload(data, meta)`, `tool_response/tool_error`, `db_session()`.

**Tasarım kararı:** tool gövdesi zarfı kurmaz, yalnızca veriyi döndürür. Zarfı
sarmalayıcı kurduğu için "`success: true` ama `data` yok" durumu **yazılamaz**
— ajanlar `tool_result["data"]` diye okuyor (`portfolio_agent.py`,
`market_agent.py`), o okuma artık yapısal olarak güvenli.

**Davranış düzeltmeleri**

| Önce | Sonra |
|---|---|
| İstisna tool sınırından kaçıyordu; fastmcp `ToolError` → ajan → orchestrator → `api/chat.py` zinciriyle **tüm SSE akışı** düşüyor, asistan mesajı `INCOMPLETE` yazılıyordu | Her hata yolu zarf içinde döner; sohbet ayakta kalır |
| Servisin iç metni kullanıcıya gidiyordu (`"Portfolio not found for user_id 6f1a…"`, `market_tools`'ta `str(exc)`) | Merkezî Türkçe mesaj gider; iç metin `WARNING`/`ERROR` olarak loglanır |
| RAG asistanının 10-20 sn'lik bloklayan yüklemesi `async def` içinde çalışıyor, ilk piyasa sorusunda **tüm süreci** donduruyordu | `anyio.to_thread.run_sync` ile thread'e alındı |
| Tool çağrıları hiç loglanmıyordu; MCP ayrı süreç olduğu için `setup_logging()` de çağrılmıyordu | `[MCP] tool=… sonuc=… sure_ms=… arg=…` + başlangıçta kayıtlı tool listesi |
| `server.py`'de kayıtlar elle, TODO yorumuyla | `register_all()` + tek `_TOOL_MODULES` listesi; yeni tool = tek satır |

**Doküman:** `docs/MCP-TOOLS.md` (zarf, taksonomi, isimlendirme/tipler,
docstring standardı, zaman aşımı, senkron/async seçimi, log, kopyala-yapıştır
iskelet, kontrol listesi, test şablonu, bilinen boşluklar). `docs/AGENTS.md`
buraya bağlandı ve ajan yazarı için özet eklendi.

**Config:** `MCP_TOOL_TIMEOUT_DEFAULT=10`, `MCP_TOOL_TIMEOUT_RAG=60`
(`.env.example`'a da eklendi). Zaman aşımı bir performans hedefi değil, asılı
kalmaya karşı emniyet supabıdır; A5'in uçtan uca ≤5 sn hedefi ayrı iş.

**Exceptions:** `InsufficientDataError`, `ProviderUnavailableError` eklendi —
servisler taksonomiye kendi istisnalarıyla bağlanabilsin diye. `INSUFFICIENT_DATA`,
"uydurmama" kuralının makineyle okunabilir hâli; risk tool'unda en çok bu
kullanılacak.

## Bilinçli kırdığım test

`get_portfolio_summary` artık `PORTFOLIO_NOT_FOUND` yerine `NOT_FOUND`
döndürüyor (ortak taksonomi). `tests/test_mcp_portfolio_tool.py` buna göre
güncellendi ve mesajın kullanıcıya sızmadığı da doğrulanıyor.

## Testler

`pytest -q` → **31 passed** (öncesi 20).

Yeni `tests/test_mcp_tool_base.py` (11 test) tool'a özel değil, **sözleşmeye**
bağlı: zarfta `data` garantisi · `meta` yalnızca istenirse · senkron gövdenin
olay döngüsünü bloklamadığı (thread adı kontrolü) · `NotFoundError` /
`InsufficientDataError` eşlemesi · `ToolFailure.detail`'ın zarfa girmemesi ·
beklenmeyen istisnanın `INTERNAL_ERROR`'a dönmesi ve metnin sızmaması · zaman
aşımı · sözleşme dışı dönüş tipi · pydantic doğrulamasının gövdeye hiç
ulaşmaması.

`tests/test_mcp_portfolio_tool.py`'a "servis beklenmeyen istisna fırlatırsa tool
çökmez" testi eklendi (bugüne kadar test edilmeyen, en riskli yol).

Ayrıca duman testi: MCP sunucusu ayağa kalkıyor, iki tool kayıtlı, docstring'ler
modele doğru biçimde gidiyor. (Bu sırada bir ayrıntı doğrulandı: FastMCP
docstring'in `Args:` kısmını argüman şemalarına koyuyor ama **`Returns:` kısmını
modele vermiyor** — dokümanda buna göre yazıldı.)

`ruff` + `black` temiz.

## Canlı/test ortamına etkisi

- `agents/`, `backend/app/api/`, `frontend/` **hiç değişmedi**.
- Ajanların okuduğu üç alan (`success`, `data`, `error.message`) birebir aynı;
  "portföyümü özetle" akışı davranış olarak aynı, biçim olarak standart.
- Değişen tek sözleşme detayı `error.code` — bunu bugün yalnızca test okuyor.
- Migration yok, veri değişikliği yok. Sorun çıkarsa tek revert yeterli.

## Kapsam dışı (bilerek)

Yeni tool eklemek (`get_holdings` vb. ayrı görev) · risk hesabı · RAG'ın
getirme/üretim ayrımı · ajanların yeniden yazımı · MCP bağlantı havuzu, istemci
tarafı zaman aşımı ve ajan başına tool yetkisi ("çoklu ajan ortamı" görevi).
Bunlar `docs/MCP-TOOLS.md` §10'da "bilinen boşluklar" olarak yazılı.

## Sonraki tool'u yazacak arkadaşlara

`docs/MCP-TOOLS.md` §8'deki iskeleti kopyala, servisini çağır, üç testi yaz,
modülünü `_TOOL_MODULES`'a ekle. Kendi zarfını, kendi `try/except`'ini, kendi
hata kodunu yazma.
