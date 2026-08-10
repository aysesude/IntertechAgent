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
