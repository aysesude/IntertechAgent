"""Uygulama genelinde kullanılan özel exception sınıfları."""


class AppError(Exception):
    """Tüm uygulama hatalarının temel sınıfı."""

    def __init__(self, message: str, *, code: str = "APP_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class NotFoundError(AppError):
    def __init__(self, message: str, *, code: str = "NOT_FOUND") -> None:
        super().__init__(message, code=code)


class ValidationAppError(AppError):
    def __init__(self, message: str, *, code: str = "VALIDATION_ERROR") -> None:
        super().__init__(message, code=code)


class InsufficientDataError(AppError):
    """Kayıt var ama hesap için veri yetersiz (ör. 60 günden kısa fiyat serisi).
    "Uydurmama" kuralının makineyle okunabilir hâli: servis tahmin üretmez,
    bunu fırlatır (AK 5.5, 5.10)."""

    def __init__(self, message: str, *, code: str = "INSUFFICIENT_DATA") -> None:
        super().__init__(message, code=code)


class ProviderUnavailableError(AppError):
    """Dış kaynak (TCMB/yfinance/Chroma/Ollama) yanıt vermiyor."""

    def __init__(self, message: str, *, code: str = "PROVIDER_UNAVAILABLE") -> None:
        super().__init__(message, code=code)
