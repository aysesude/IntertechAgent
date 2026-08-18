> **Geçici çalışma notu — 18 Ağustos 2026.** `risk-agent-yagiz` dalını sözleşmeye hizalamak için tek seferlik talimat; iş bitince güncelliğini yitirir. Kalıcı kurallar [`docs/MCP-TOOLS.md`](../MCP-TOOLS.md)'de.

# Not: `risk-agent-yagiz` dalını MCP tool sözleşmesine hizalama

> Bu not, `risk-agent-yagiz` dalında çalışan geliştirici (ve onun yapay zekâ
> asistanı) içindir. Amaç: risk tool'unu yeniden yazmak değil, **sözleşmeye
> oturtmak.** Servis katmanına, risk metodolojisine, şemalara dokunulmuyor.
> Tahmini süre: 20-30 dakika.

## Bağlam

`feature/mcp-tool-sozlesmesi` dalı (PR: `test` dalına) tüm MCP tool'ları için
ortak bir zemin ekledi: tek dönüş zarfı, sabit hata kümesi, zaman aşımı,
loglama. Sözleşmenin tamamı repo'da: **`docs/MCP-TOOLS.md`** — bu notu
uygulamadan önce en azından §1, §2, §8 okunmalı.

`risk-agent-yagiz` dalı bu zemin yokken yazıldı; bugünkü hâliyle iki noktada
sözleşmeden sapıyor ve `mcp_server/server.py`'de çakışacak.

## Ön koşul

Sözleşme PR'ı `test`'e merge edildikten **sonra** yapılır:

```bash
git checkout risk-agent-yagiz
git fetch origin
git merge origin/test          # veya: git rebase origin/test
```

Çakışma yalnızca `mcp_server/server.py` ve `mcp_server/tools/risk_tools.py`
dosyalarında beklenir; ikisinin de çözümü aşağıda.

## 1. `mcp_server/server.py` — kayıt satırını geri al

Sözleşme sonrası kayıtlar tek listede toplanıyor. `risk_tools.register(mcp)`
satırı **eklenmez**; bunun yerine modül listeye girer:

```python
# ÖNCE (bu daldaki hâli — çakışmada bu taraf ATILIR)
portfolio_tools.register(mcp)
market_tools.register(mcp)
risk_tools.register(mcp)

# SONRA (test dalındaki hâline şu tek değişiklik yapılır)
_TOOL_MODULES = [portfolio_tools, market_tools, risk_tools]
```

`risk_tools` importunu `from mcp_server.tools import market_tools, portfolio_tools, risk_tools`
biçiminde bırakmak yeterli. `register_all()` fonksiyonuna ve log satırına
dokunma.

## 2. `mcp_server/tools/risk_tools.py` — hedef hâli

Aşağıdaki dosya, bu dalda yazılmış tool'un sözleşmeye uygun sürümüdür.
`app/services/risk_service.py` ve `app/schemas/risk.py` **değişmiyor**;
sadece tool katmanı sadeleşiyor.

```python
"""get_risk_assessment MCP tool'u. Veriye doğrudan erişmez; her zaman
app.services.risk_service üzerinden okur. Sayısal hiçbir değer burada
hesaplanmaz, servis katmanından geldiği gibi döner.

Risk eşikleri, ağırlıklar ve hedef dağılımlar app/core/config.py'de tanımlıdır.
Sözleşme: docs/MCP-TOOLS.md
"""

from typing import Any
from uuid import UUID

from fastmcp import FastMCP

from app.core.config import RiskProfile
from app.services.risk_service import get_risk_assessment as fetch_risk_assessment
from mcp_server.tools._base import db_session, tool_handler


def register(mcp: FastMCP) -> list[str]:
    @mcp.tool(name="get_risk_assessment")
    @tool_handler()
    def get_risk_assessment(
        user_id: UUID, profile_override: RiskProfile | None = None
    ) -> dict[str, Any]:
        """Bir kullanıcının portföy riskini değerlendirir ve yeniden dengeleme
        önerisi üretir: risk skoru (0-100), risk etiketi, yıllıklandırılmış
        volatilite, korelasyon matrisi, kovaryans tabanlı portföy volatilitesi,
        VaR, Sharpe oranı, yoğunlaşma/çeşitlendirme metrikleri ve varlık sınıfı
        bazlı alım/satım önerisi. Tüm sayısal değerler veritabanından hesaplanır.

        Ne zaman kullanılır: "riskim ne durumda", "portföyüm ne kadar riskli",
        "yeniden dengeleme önerisi", "profilime uygun mu" gibi sorular.

        Ne zaman kullanılmaz: yalnızca değer/dağılım soruluyorsa
        (get_portfolio_summary), piyasa haberi/bilanço soruluyorsa
        (search_market_news).

        Args:
            user_id: Risk değerlendirmesi istenen kullanıcının UUID'si.
            profile_override: Verilirse hesaplama bu risk profiline göre yapılır
                (conservative | balanced | aggressive). Kullanıcının kayıtlı
                profili değişmez — "ya agresif olsaydım?" senaryosu içindir.
                Verilmezse kullanıcının kayıtlı profili kullanılır.

        Returns:
            Başarılı: {"success": true, "data": {...risk değerlendirmesi...}}
            Hata: {"success": false, "error": {"code": "NOT_FOUND" |
            "INSUFFICIENT_DATA" | "INTERNAL_ERROR", "message": "..."}}
        """
        with db_session() as db:
            return fetch_risk_assessment(db, user_id, profile_override).model_dump(mode="json")

    return ["get_risk_assessment"]
```

Silinen üç şey ve nedeni:

1. **`try/except NotFoundError` bloğu** — `@tool_handler` `NotFoundError`'ı
   otomatik `NOT_FOUND` koduna eşliyor. Tool'un istisna yakalaması gerekmiyor;
   yakalarsa merkezî Türkçe mesaj devreye giremez.
2. **`RISK_TARGET_NOT_FOUND` kodu** — hata kodları sabit bir kümeden gelir
   (`ToolErrorCode`). Alan adına özel kod eklenmez: ajan tarafında her kod için
   ayrı özel durum yazmak zorunda kalmayalım diye. Kod: `NOT_FOUND`.
3. **`exc.message`'ın zarfa konması** — servis istisnalarının metni İngilizce ve
   tekniktir (`"Risk target not found for profile ..."`); bu metin ajan üzerinden
   **kullanıcının ekranına** gidiyor. Artık merkezî Türkçe mesaj gidiyor, iç
   metin loglanıyor.
4. **`SessionLocal()` + `finally: db.close()`** — `db_session()` context
   manager'ı aynı işi yapıyor.

## 3. Risk servisinde: yetersiz veri → uydurma

Bu, risk tool'unu en çok ilgilendiren sözleşme maddesi. `risk_service`
volatilite/korelasyon/VaR hesaplarken fiyat serisi kısa ya da ortak gün sayısı
yetersizse **varsayımla doldurmamalı**, şunu fırlatmalı:

```python
from app.core.exceptions import InsufficientDataError

raise InsufficientDataError(
    f"only {gun_sayisi} of {gereken_gun} required days available for {sembol}"
)
```

`@tool_handler` bunu `INSUFFICIENT_DATA` koduna çevirir ve kullanıcıya
"Bu hesaplama için yeterli veri yok; tahmin üretmemek adına sonuç verilmedi."
mesajı gider. Bu, CLAUDE.md'nin "uydurmama" kuralının (AK 5.5, 5.10) makineyle
okunabilir hâli — risk motorunda en çok bu kod kullanılacak.

Servis bugün bu durumda ne yapıyorsa (0 dönmek, kısa seriyle hesaplamak,
`None` yaymak) gözden geçirilmeli. Metodolojiyi değiştirme; yalnızca "veri
yetmiyorsa sonuç üretme" davranışını netleştir.

## 4. Testler

`tests/test_mcp_risk_tool.py` içinde:

- Beklenen hata kodu `"RISK_TARGET_NOT_FOUND"` → `ToolErrorCode.NOT_FOUND.value`
  olarak güncellenir (`from mcp_server.tools._base import ToolErrorCode`).
- Şu test eklenir (bugün test edilmeyen en riskli yol — istisna tool sınırından
  kaçarsa yalnızca risk ajanı değil **tüm SSE sohbeti** düşer):

```python
async def test_get_risk_assessment_beklenmeyen_hatada_cokmez(mcp_server, monkeypatch):
    def patlat(db, user_id, profile_override=None):
        raise SQLAlchemyError("connection failed")

    monkeypatch.setattr(risk_tools, "fetch_risk_assessment", patlat)

    async with Client(mcp_server) as client:
        result = await client.call_tool("get_risk_assessment", {"user_id": str(uuid.uuid4())})

    assert result.structured_content["error"]["code"] == ToolErrorCode.INTERNAL_ERROR.value
```

- Yeterli veri yoksa `INSUFFICIENT_DATA` döndüğü de test edilmeli (§3).

Zarf/zaman aşımı/log gibi **ortak** davranışlar `tests/test_mcp_tool_base.py`'de
bir kez test edildi; tekrar etme.

## 5. Dokunulmayacaklar

- `mcp_server/tools/_base.py` — sözleşmenin kendisi. Eksik gördüğün bir hata
  kodu varsa **ekleme, konuş**: taksonomi sabit olduğu için değerli.
- `agents/`, `backend/app/api/`, `frontend/` — bu iş tool katmanıyla sınırlı.
- Risk metodolojisi (SRRI bantları, kovaryans, VaR, Sharpe) — bu notun konusu
  değil; eşik kalibrasyonu analist onayı bekliyor.

## 6. Bitti sayma kriteri

```bash
# Docker kapalıysa:
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m ruff check .
./.venv/Scripts/python.exe -m black --check .
```

- Tüm testler yeşil.
- `python -m mcp_server.server` başlarken log satırında üç tool görünüyor:
  `[MCP] 3 tool kayitli: get_portfolio_summary, get_risk_assessment, search_market_news`
- `risk_tools.py` içinde `try`, `except`, `SessionLocal`, `success`, `error`
  kelimelerinin hiçbiri geçmiyor (zarfı ve hatayı sarmalayıcı yönetiyor).
- PR açıklamasında hangi FR/US/AK'ya bağlandığı ve bilinçli kırılan test yazılı.

## 7. Kontrol listesi (docs/MCP-TOOLS.md §8'in kısası)

- [ ] Gövde zarf kurmuyor, yalnızca `dict` döndürüyor
- [ ] `except` yok; beklenen başarısızlık `ToolFailure` / servis istisnası
- [ ] Hata kodu sabit kümeden (`ToolErrorCode`)
- [ ] `error.message`'a iç metin konmuyor
- [ ] Docstring'de "Ne zaman kullanılmaz" satırı var, komşu tool'ları anıyor
- [ ] Modül `_TOOL_MODULES`'a eklendi, `register()` tool adını döndürüyor
- [ ] Üç test: başarı, `NOT_FOUND`, beklenmeyen istisna → `INTERNAL_ERROR`
