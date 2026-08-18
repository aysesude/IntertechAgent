"""MCP tool'larının ortak zemini: dönüş zarfı, hata taksonomisi, zaman aşımı,
loglama ve DB oturumu. Sözleşmenin yazılı hâli `docs/MCP-TOOLS.md`; bu dosya
onun uygulamasıdır.

Temel kural: **tool gövdesi zarfı kurmaz.** Gövde yalnızca veriyi döndürür
(`dict` ya da `ToolPayload`) veya beklenen bir başarısızlıkta `ToolFailure`
fırlatır. Zarfı `@tool_handler` kurar. Böylece "success: true ama data yok"
durumu yazılamaz hâle gelir — ajanlar `tool_result["data"]` diye okuyor
(bkz. agents/portfolio_agent.py), o okuma artık güvenli.

`@tool_handler` dört işi tek yerde toplar:
  1. zarf        — başarı/hata biçimi istisnasız aynı,
  2. taksonomi   — servis istisnası → sabit hata kodu (ToolErrorCode),
  3. zaman aşımı — asılı kalan çağrı zarf içinde TIMEOUT'a döner,
  4. log         — tool adı, argüman özeti, süre, sonuç.

Gövde senkron da (`def`) asenkron da (`async def`) yazılabilir: sarmalayıcı her
zaman `async`'tir, senkron gövdeyi worker thread'e alır. Böylece DB tool'ları
sade `def` kalırken olay döngüsü bloklanmaz, RAG/dış ağ tool'ları `async def`
yazılabilir; ikisi de aynı zarfı, aynı zaman aşımını ve aynı logu alır.
"""

import functools
import inspect
import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any

import anyio
import anyio.to_thread
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


class ToolErrorCode(str, Enum):
    """Tüm tool'ların paylaştığı sabit hata kümesi. Alan adına özel kod
    (ör. PORTFOLIO_NOT_FOUND) eklenmez: ajan tarafında her kod için ayrı bir
    özel durum yazmak zorunda kalmayalım diye küme sabit tutulur.

    Ayrılmış (henüz kullanılmıyor): UNAUTHORIZED — ajan başına tool yetkisi
    geldiğinde (AK 5.4, "çoklu ajan ortamı" görevi).
    """

    NOT_FOUND = "NOT_FOUND"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# Kullanıcıya gösterilen metinler tek yerde durur: bugün zarftaki mesaj fiilen
# ekrana gidiyor (tool -> ajan -> orchestrator -> SSE). Metin tool dosyalarına
# dağılırsa hem üslup tutmaz hem de ileride "metni sunum katmanı yazsın"
# kararına geçmek zorlaşır. Metinler Türkçe, kısa ve teknik ayrıntısızdır.
DEFAULT_MESSAGES: dict[ToolErrorCode, str] = {
    ToolErrorCode.NOT_FOUND: "İstenen kayıt bulunamadı.",
    ToolErrorCode.INSUFFICIENT_DATA: (
        "Bu hesaplama için yeterli veri yok; tahmin üretmemek adına sonuç verilmedi."
    ),
    ToolErrorCode.INVALID_ARGUMENT: "İstek anlamlı değil, lütfen sorunuzu netleştirin.",
    ToolErrorCode.PROVIDER_UNAVAILABLE: (
        "Veri kaynağına şu anda ulaşılamıyor. Lütfen biraz sonra tekrar deneyin."
    ),
    ToolErrorCode.TIMEOUT: "İşlem beklenenden uzun sürdü ve tamamlanamadı.",
    ToolErrorCode.INTERNAL_ERROR: "Beklenmeyen bir sorun oluştu, isteğiniz tamamlanamadı.",
}

# app/core/exceptions.py'deki AppError.code -> tool hata kodu eşlemesi. Servisler
# kendi istisnalarını fırlatır; tool bunları tek tek tanımak zorunda kalmaz.
APP_ERROR_CODE_MAP: dict[str, ToolErrorCode] = {
    "NOT_FOUND": ToolErrorCode.NOT_FOUND,
    "VALIDATION_ERROR": ToolErrorCode.INVALID_ARGUMENT,
    "INSUFFICIENT_DATA": ToolErrorCode.INSUFFICIENT_DATA,
    "PROVIDER_UNAVAILABLE": ToolErrorCode.PROVIDER_UNAVAILABLE,
}

# Log satırındaki argüman özetinde tek bir değerin kaplayacağı azami uzunluk.
_MAX_LOGGED_ARG_LENGTH = 60


@dataclass(frozen=True)
class ToolPayload:
    """Gövde `meta` de döndürmek istiyorsa bunu kullanır (bkz. AK 5.3: veri
    kaynağı + zaman damgası). Veri gövdesinde zaten karşılığı olan bilgi
    (ör. `as_of`) meta'ya kopyalanmaz — iki kaynak doğurur."""

    data: dict[str, Any]
    meta: dict[str, Any] | None = None


class ToolFailure(Exception):
    """Gövdenin **beklenen** başarısızlığı bildirme yolu. `@tool_handler` bunu
    zarfa çevirir; `detail` yalnızca loga yazılır, kullanıcıya gitmez."""

    def __init__(
        self,
        code: ToolErrorCode,
        message: str | None = None,
        *,
        detail: str | None = None,
    ) -> None:
        self.code = code
        self.message = message or DEFAULT_MESSAGES[code]
        self.detail = detail
        super().__init__(self.message)


def tool_response(data: dict[str, Any], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Başarı zarfı. `data` her zaman bulunur (boş sözlük olabilir, None olamaz)."""
    envelope: dict[str, Any] = {"success": True, "data": data}
    if meta:
        envelope["meta"] = meta
    return envelope


def tool_error(code: ToolErrorCode, message: str | None = None) -> dict[str, Any]:
    """Hata zarfı. Mesaj kullanıcıya gösterilebilir olmalıdır: istisna metni,
    SQL, bağlantı adresi veya dosya yolu buraya KONULMAZ (bunlar loga gider)."""
    return {
        "success": False,
        "error": {"code": code.value, "message": message or DEFAULT_MESSAGES[code]},
    }


@contextmanager
def db_session() -> Iterator[Session]:
    """Tool'lar için DB oturumu: her tool'un elle `SessionLocal()` açıp
    `finally`'de kapatması yerine tek kalıp."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _short(value: Any) -> str:
    text = str(value)
    if len(text) > _MAX_LOGGED_ARG_LENGTH:
        return text[:_MAX_LOGGED_ARG_LENGTH] + "..."
    return text


def _summarize_arguments(kwargs: dict[str, Any]) -> str:
    if not kwargs:
        return "-"
    return ", ".join(f"{key}={_short(value)}" for key, value in kwargs.items())


def tool_handler(
    *, name: str | None = None, timeout: float | None = None
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """MCP tool gövdesini ortak sözleşmeye bağlayan sarmalayıcı.

    `@mcp.tool(...)`'un ALTINA konur:

        @mcp.tool(name="get_holdings")
        @tool_handler()
        def get_holdings(user_id: UUID) -> dict[str, Any]:
            # docstring: bkz. docs/MCP-TOOLS.md
            with db_session() as db:
                return ...

    Args:
        name: Log satırında görünecek ad. Verilmezse fonksiyon adı kullanılır.
        timeout: Saniye. Verilmezse `settings.mcp_tool_timeout_default`.
            Bu bir performans hedefi değil, asılı kalmaya karşı emniyet
            supabıdır. Uyarı: senkron gövdede süre dolduğunda çağıran taraf
            TIMEOUT zarfını alır ama thread arkada çalışmaya devam eder —
            Python'da senkron kod dışarıdan iptal edilemez.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        tool_name = name or fn.__name__
        limit = timeout if timeout is not None else settings.mcp_tool_timeout_default
        is_async = inspect.iscoroutinefunction(fn)

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            started = time.perf_counter()
            outcome = "OK"
            try:
                with anyio.fail_after(limit):
                    if is_async:
                        result = await fn(*args, **kwargs)
                    else:
                        # Senkron gövde olay döngüsünü bloklamasın diye thread'e
                        # alınır. abandon_on_cancel=True: zaman aşımında beklemeden
                        # döneriz; aksi hâlde thread bitene kadar beklenirdi ve
                        # zaman aşımı fiilen işlemezdi.
                        result = await anyio.to_thread.run_sync(
                            functools.partial(fn, *args, **kwargs), abandon_on_cancel=True
                        )

                if isinstance(result, ToolPayload):
                    return tool_response(result.data, result.meta)
                if not isinstance(result, dict):
                    raise TypeError(
                        "Tool gövdesi dict veya ToolPayload döndürmeli, "
                        f"{type(result).__name__} döndü."
                    )
                return tool_response(result)

            except ToolFailure as exc:
                outcome = exc.code.value
                logger.warning(
                    "[MCP] tool=%s beklenen hata kod=%s detay=%s",
                    tool_name,
                    exc.code.value,
                    exc.detail or "-",
                )
                return tool_error(exc.code, exc.message)

            except AppError as exc:
                code = APP_ERROR_CODE_MAP.get(exc.code, ToolErrorCode.INTERNAL_ERROR)
                outcome = code.value
                # exc.message servis katmanının iç metnidir (İngilizce, teknik):
                # yalnızca loga yazılır; zarfa merkezî Türkçe metin konur.
                logger.warning(
                    "[MCP] tool=%s servis hatasi kod=%s ic_mesaj=%s",
                    tool_name,
                    code.value,
                    exc.message,
                )
                return tool_error(code)

            except TimeoutError:
                outcome = ToolErrorCode.TIMEOUT.value
                logger.warning("[MCP] tool=%s zaman asimi limit=%.1fs", tool_name, limit)
                return tool_error(ToolErrorCode.TIMEOUT)

            except Exception:  # noqa: BLE001 - tool sınırında istisna sızdırılmaz
                outcome = ToolErrorCode.INTERNAL_ERROR.value
                # Buradan istisna kaçarsa yalnızca ajan değil TÜM sohbet düşer:
                # fastmcp ToolError -> agents/base.py -> orchestrator -> SSE.
                logger.exception("[MCP] tool=%s beklenmeyen istisna", tool_name)
                return tool_error(ToolErrorCode.INTERNAL_ERROR)

            finally:
                logger.info(
                    "[MCP] tool=%s sonuc=%s sure_ms=%.0f arg=%s",
                    tool_name,
                    outcome,
                    (time.perf_counter() - started) * 1000,
                    _summarize_arguments(kwargs),
                )

        return wrapper

    return decorator
