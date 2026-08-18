# MCP Tool Sözleşmesi

Ajanların veriye erişebildiği tek yol MCP tool'larıdır. Bu hafta tool sayısı
2'den ~10'a çıkacak ve tool'lar farklı kişiler tarafından paralel yazılacak;
bu doküman **hepsinin uyacağı sözleşmedir**. Uygulaması
`mcp_server/tools/_base.py`, referans örneği
`mcp_server/tools/portfolio_tools.py`.

Kısa özet: **tool veriyi döndürür, zarfı altyapı kurar, hata asla dışarı
kaçmaz, iç hata metni kullanıcıya gitmez.**

---

## 1. Dönüş zarfı

Her tool, istisnasız, şu iki biçimden birini döndürür:

```jsonc
// başarı
{
  "success": true,
  "data": { /* tool'a özel yapısal veri — HER ZAMAN var, boş olabilir ama null olamaz */ },
  "meta": { "source": "tcmb", "fetched_at": "2026-08-17T09:12:00Z" }   // opsiyonel
}

// hata
{
  "success": false,
  "error": { "code": "NOT_FOUND", "message": "İstenen kayıt bulunamadı." }
}
```

Kurallar:

- **`data` başarı durumunda her zaman bulunur.** Ajanlar `tool_result["data"]`
  diye okuyor (`agents/portfolio_agent.py`, `agents/market_agent.py`); alanın
  yokluğu ajanı `KeyError` ile düşürür. Bu yüzden zarfı tool gövdesi değil
  `@tool_handler` kurar — "success: true ama data yok" **yazılamaz**.
- **`error.message` kullanıcıya gösterilebilir olmalıdır**, çünkü fiilen
  gösteriliyor: tool → ajan (`AgentResponse.error`) → `merge_responses` →
  SSE → ekran. İstisna metni, SQL, dosya yolu, bağlantı adresi buraya
  **konmaz**; bunlar yalnızca loga yazılır.
- **`error.detail` diye bir alan yoktur.** Teknik ayrıntı `ToolFailure(...,
  detail=...)` ile verilir ve sadece loga düşer.
- `meta` yalnızca veri gövdesinde karşılığı olmayan bilgi içindir (kaynak,
  çekilme zamanı — AK 5.3). Gövdede zaten `as_of` varsa meta'ya kopyalanmaz.

## 2. Hata taksonomisi

Alan adına özel kod (`PORTFOLIO_NOT_FOUND`, `RAG_ERROR`) **yazılmaz**; küme
sabittir (`ToolErrorCode`):

| Kod | Ne zaman | Ajan ne yapmalı |
|---|---|---|
| `NOT_FOUND` | İstenen kayıt yok (kullanıcı, portföy, sembol) | Kullanıcıya nazikçe söyler |
| `INSUFFICIENT_DATA` | Kayıt var ama hesap için veri yetersiz (ör. 60 günden kısa seri) | **Tahmin üretmez**, "hesaplanamıyor" der (AK 5.5, 5.10) |
| `INVALID_ARGUMENT` | Argüman tipi doğru ama anlamsız (ör. `start > end`) | Soruyu netleştirir |
| `PROVIDER_UNAVAILABLE` | Dış kaynak (TCMB / yfinance / Chroma / Ollama) yanıt vermiyor | Son bilinen veriyle devam eder veya durumu söyler |
| `TIMEOUT` | Süre sınırı aşıldı | Aynı şekilde zarif düşüş |
| `INTERNAL_ERROR` | Beklenmeyen istisna | Genel mesaj; iç metin kullanıcıya gitmez |

`UNAUTHORIZED` ileride ayrıldı (ajan başına tool yetkisi, AK 5.4) — bugün yok.

**Servis istisnaları otomatik eşlenir**, tool bunları tek tek yakalamaz:

| `app/core/exceptions.py` | → | Tool kodu |
|---|---|---|
| `NotFoundError` | → | `NOT_FOUND` |
| `ValidationAppError` | → | `INVALID_ARGUMENT` |
| `InsufficientDataError` | → | `INSUFFICIENT_DATA` |
| `ProviderUnavailableError` | → | `PROVIDER_UNAVAILABLE` |
| diğer her şey | → | `INTERNAL_ERROR` (loglanır) |

⚠️ **`INVALID_ARGUMENT` tip hatası için değildir.** Tip/format hatasını
(`user_id="abc"`) FastMCP pydantic ile tool gövdesine girmeden reddeder ve
istisna fırlatır — zarfa hiç dönüşmez. `INVALID_ARGUMENT`, "tipi doğru ama
anlamı yanlış" durumlar içindir.

## 3. İsimlendirme, tipler, sınırlar

- Tool adı `fiil_nesne`, snake_case, İngilizce: `get_portfolio_summary`,
  `search_financial_documents`.
- Argümanlar **tiplenir**: `UUID`, `date`, `Enum`, `int`. String alıp içeride
  parse etmek yok — doğrulamayı FastMCP/pydantic yapar.
- Para/fiyat servis katmanında `Decimal`; JSON'a giderken float
  (`app/schemas/portfolio.py::Money` kalıbı). Tarihler ISO 8601 string.
- **Tool hesap yapmaz, SQL yazmaz.** Yalnızca `app/services/*` çağırır.
  (Bugünkü tek istisna `market_tools`'un `rag/retriever.py` üzerinden Chroma'yı
  çağırması — saf getirme, LLM/hesap yok, bu yüzden servis katmanı gerekmiyor.)
- Tool çıktısına "Bu bir yatırım tavsiyesi değildir" **gömülmez**; sorumluluk
  reddi sunum katmanının işidir (CLAUDE.md).

## 4. Docstring standardı

Docstring dokümantasyon değil, **prompt parçasıdır**: FastMCP ilk paragrafları
tool açıklaması, `Args:` satırlarını her argümanın JSON şema açıklaması olarak
modele verir. (`Returns:` bölümü modele **gitmez** — o insan içindir; modelin
gördüğü çıktı bilgisi output schema'dır.)

```
Tek cümlelik ne yaptığı.

Ne zaman kullanılır: ...
Ne zaman kullanılmaz: ...   ← komşu tool'la karışmayı engelleyen satır
Args: her argüman, birimi ve kabul ettiği değerler
Returns: başarı ve hata durumunda dönen yapı + kısa örnek (insan için)
```

"Ne zaman kullanılmaz" satırı zorunlu: Portföy Ajanı yakında dört tool arasından
(`summary` / `holdings` / `performance` / `transactions`) seçim yapacak ve bu
seçimi docstring'lere bakarak yapacak.

## 5. Zaman aşımı

`@tool_handler(timeout=...)`, verilmezse `settings.mcp_tool_timeout_default`
(10 sn). RAG/dış ağ tool'ları için `settings.mcp_tool_timeout_rag` (60 sn).
Değerler `.env`'den ezilebilir.

Bu bir performans hedefi değil, **asılı kalmaya karşı emniyet supabıdır**;
uçtan uca ≤5 sn hedefi (A5) ayrı bir iş.

⚠️ Senkron gövdede süre dolduğunda çağıran taraf `TIMEOUT` zarfını alır ama
**thread arkada çalışmaya devam eder** — Python'da senkron kod dışarıdan iptal
edilemez. Uzun sürecek işi baştan `async` yazmak daha iyidir.

## 6. Senkron mu, async mi?

İkisi de serbest; seçim tool'un işine göre:

- **DB okuyan tool → sade `def`.** Sarmalayıcı gövdeyi worker thread'e alır,
  olay döngüsü bloklanmaz (test: `test_senkron_govde_olay_dongusunu_bloklamaz`).
- **Dış ağ/LLM çağıran tool → `async def`**, içindeki **bloklayan** çağrılar
  (model yükleme, senkron istemciler) `anyio.to_thread.run_sync` ile thread'e
  alınır. `async def` içinde bloklayan kod olay döngüsünü durdurur: bir istek
  değil, **tüm süreç** donar.

## 7. Loglama

Her çağrı için tek satır, `@tool_handler` yazar:

```
[MCP] tool=get_portfolio_summary sonuc=OK sure_ms=41 arg=user_id=6f1a...
[MCP] tool=search_market_news sonuc=TIMEOUT sure_ms=60002 arg=query=enflasyon..., session_id=...
```

Hata yollarında ayrıca bir `WARNING`/`ERROR` satırı düşer ve **iç metin oraya**
yazılır (zarfa değil). MCP sunucusu ayrı bir süreç olduğu için
`mcp_server/server.py` kendi `setup_logging()` çağrısını yapar.

---

## 8. Yeni tool eklerken (kopyala-yapıştır)

```python
"""<tool ailesi> tool'ları."""

from typing import Any
from uuid import UUID

from fastmcp import FastMCP

from app.services.<x>_service import <fonksiyon>
from mcp_server.tools._base import db_session, tool_handler


def register(mcp: FastMCP) -> list[str]:
    @mcp.tool(name="get_something")
    @tool_handler()                       # dış ağ ise: timeout=settings.mcp_tool_timeout_rag
    def get_something(user_id: UUID) -> dict[str, Any]:
        """Tek cümlelik ne yaptığı.

        Ne zaman kullanılır: ...
        Ne zaman kullanılmaz: ...

        Args:
            user_id: ...

        Returns:
            Başarılı: {"success": true, "data": {...}}
            Hata: {"success": false, "error": {"code": "NOT_FOUND", ...}}
        """
        with db_session() as db:
            return <fonksiyon>(db, user_id).model_dump(mode="json")

    return ["get_something"]
```

Sonra `mcp_server/server.py` içindeki `_TOOL_MODULES` listesine modülü ekle —
başka hiçbir yere dokunmak gerekmez.

**Kontrol listesi**

- [ ] Gövde zarf kurmuyor; sadece `dict` (veya `ToolPayload`) döndürüyor.
- [ ] Beklenen başarısızlıklar `ToolFailure(ToolErrorCode.X)` ile bildiriliyor;
      teknik ayrıntı `detail=` içinde (zarfa değil, loga).
- [ ] `except Exception` yok — sarmalayıcı hallediyor.
- [ ] Argümanlar tiplenmiş; string parse'ı yok.
- [ ] Docstring'de "Ne zaman kullanılmaz" satırı var, komşu tool'ları anıyor.
- [ ] Hesap/SQL yok; yalnızca `app/services/*` çağrılıyor.
- [ ] Modül `_TOOL_MODULES`'a eklendi, `register()` tool adlarını döndürüyor.
- [ ] Üç test yazıldı (aşağıdaki şablon).
- [ ] `make test` ve `make lint` yeşil.

## 9. Test şablonu

Her tool için en az üç durum. Zarf/taksonomi/zaman aşımı gibi **ortak**
davranışlar `tests/test_mcp_tool_base.py`'de bir kez test edilmiştir; tekrar
etmeye gerek yok.

```python
import uuid

import pytest
from fastmcp import Client, FastMCP
from sqlalchemy.exc import SQLAlchemyError

from mcp_server.tools import x_tools
from mcp_server.tools._base import ToolErrorCode


@pytest.fixture()
def mcp_server():
    mcp = FastMCP("test-finans-mcp")
    x_tools.register(mcp)
    return mcp


async def test_get_something_success(mcp_server, seeded_user): ...


async def test_get_something_not_found(mcp_server, db_session):
    async with Client(mcp_server) as client:
        result = await client.call_tool("get_something", {"user_id": str(uuid.uuid4())})
    assert result.structured_content["error"]["code"] == ToolErrorCode.NOT_FOUND.value


async def test_get_something_beklenmeyen_hatada_cokmez(mcp_server, monkeypatch):
    def patlat(db, user_id):
        raise SQLAlchemyError("connection failed")

    monkeypatch.setattr(x_tools, "<import edilen servis fonksiyonu>", patlat)
    async with Client(mcp_server) as client:
        result = await client.call_tool("get_something", {"user_id": str(uuid.uuid4())})
    assert result.structured_content["error"]["code"] == ToolErrorCode.INTERNAL_ERROR.value
```

Testler `.venv` ile Docker'sız da koşar: `pytest -q` (SQLite üzerinde).

## 10. Bu sözleşmenin kapsamadığı, bilinen boşluklar

- **İstemci tarafı zaman aşımı yok.** `agents/base.py::call_mcp_tool` her çağrıda
  yeni `Client` açıyor ve süre sınırı vermiyor; sunucu hiç yanıt vermezse ajan
  asılı kalır. MCP bağlantı havuzuyla birlikte "çoklu ajan ortamı" görevinde.
- **Ajan başına tool yetkisi yok** (AK 5.4) — her ajan her tool'u çağırabilir.
