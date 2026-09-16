from __future__ import annotations


class MaxApiError(RuntimeError):
    def __init__(self, status: int, code: str = "", message: str = "") -> None:
        self.status = status
        self.code = code
        self.message = message
        super().__init__(f"MAX API {status}: {code or 'error'} {message}".strip())

    @property
    def is_auth_error(self) -> bool:
        return self.status == 401

    @property
    def is_rate_limited(self) -> bool:
        return self.status == 429

    @property
    def is_retriable(self) -> bool:
        return self.status == 429 or self.status >= 500


class MaxNetworkError(RuntimeError):
    pass
