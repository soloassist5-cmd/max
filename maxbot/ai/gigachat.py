from __future__ import annotations

import asyncio
import logging
import ssl
import time
import uuid
from typing import Any, Mapping, Sequence

import aiohttp

log = logging.getLogger(__name__)

OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
API_BASE = "https://api.giga.chat/v1"
DEFAULT_SCOPE = "GIGACHAT_API_PERS"
DEFAULT_MODEL = "GigaChat"

TOKEN_LIFETIME = 30 * 60
TOKEN_LEEWAY = 60  # обновляем чуть раньше, чем токен реально протухнет
DEFAULT_RETRIES = 3


class GigaChatError(RuntimeError):
    def __init__(self, status: int, message: str = "") -> None:
        self.status = status
        self.message = message
        super().__init__(f"GigaChat {status}: {message}".strip())

    @property
    def is_auth_error(self) -> bool:
        return self.status == 401

    @property
    def is_retriable(self) -> bool:
        return self.status == 429 or self.status >= 500


class GigaChatNetworkError(RuntimeError):
    pass


def parse_expires_at(value: Any) -> float:
    """expires_at приходит то в секундах, то в миллисекундах."""
    try:
        moment = float(value)
    except (TypeError, ValueError):
        return time.time() + TOKEN_LIFETIME
    if moment > 1e12:
        moment /= 1000.0
    return moment


class GigaChatClient:
    def __init__(
        self,
        auth_key: str,
        *,
        scope: str = DEFAULT_SCOPE,
        model: str = DEFAULT_MODEL,
        api_base: str = API_BASE,
        oauth_url: str = OAUTH_URL,
        ca_bundle: str | None = None,
        verify_ssl: bool = True,
        session: aiohttp.ClientSession | None = None,
        retries: int = DEFAULT_RETRIES,
    ) -> None:
        self._auth_key = auth_key
        self._scope = scope
        self._model = model
        self._api_base = api_base.rstrip("/")
        self._oauth_url = oauth_url
        self._ca_bundle = ca_bundle
        self._verify_ssl = verify_ssl
        self._session = session
        self._owns_session = session is None
        self._retries = retries

        self._token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    @property
    def model(self) -> str:
        return self._model

    async def __aenter__(self) -> "GigaChatClient":
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def start(self) -> None:
        if self._session is not None:
            return
        connector = aiohttp.TCPConnector(ssl=self._ssl_context())
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=15, sock_read=120),
        )
        self._owns_session = True

    async def close(self) -> None:
        if self._session is not None and self._owns_session:
            await self._session.close()
        self._session = None

    def _ssl_context(self) -> ssl.SSLContext | bool:
        if not self._verify_ssl:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            return context
        if self._ca_bundle:
            return ssl.create_default_context(cafile=self._ca_bundle)
        return True

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            await self.start()
        assert self._session is not None
        return self._session

    async def access_token(self, *, force: bool = False) -> str:
        """Токен живёт 30 минут, поэтому держим его в памяти и обновляем по сроку."""
        async with self._token_lock:
            if not force and self._token and time.time() < self._token_expires_at - TOKEN_LEEWAY:
                return self._token

            session = await self._ensure_session()
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "RqUID": str(uuid.uuid4()),
                "Authorization": f"Basic {self._auth_key}",
            }
            try:
                async with session.post(
                    self._oauth_url, headers=headers, data={"scope": self._scope},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    payload = await _read_json(response)
                    if response.status != 200:
                        raise GigaChatError(response.status, _error_message(payload))
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                raise GigaChatNetworkError(f"не удалось получить токен: {exc}") from exc

            token = payload.get("access_token") if isinstance(payload, dict) else None
            if not token:
                raise GigaChatError(200, "в ответе нет access_token")

            self._token = str(token)
            self._token_expires_at = parse_expires_at(payload.get("expires_at"))
            return self._token

    async def chat(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        response_format: Mapping[str, Any] | None = None,
    ) -> str:
        """Возвращает текст ответа модели.

        Системное сообщение должно быть первым и единственным, иначе API вернёт 422.
        """
        body: dict[str, Any] = {"model": model or self._model, "messages": list(messages)}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if temperature is not None:
            body["temperature"] = temperature
        if response_format is not None:
            body["response_format"] = dict(response_format)

        payload = await self._post("/chat/completions", body)
        choices = payload.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return str(message.get("content") or "").strip()

    async def models(self) -> list[str]:
        payload = await self._post("/models", None, method="GET")
        return [item.get("id", "") for item in (payload.get("data") or []) if isinstance(item, dict)]

    async def _post(self, path: str, body: Any, *, method: str = "POST") -> dict[str, Any]:
        session = await self._ensure_session()
        url = f"{self._api_base}{path}"
        refreshed = False
        delay = 1.0

        for attempt in range(self._retries):
            token = await self.access_token(force=refreshed)
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "X-Request-ID": str(uuid.uuid4()),
            }
            try:
                async with session.request(
                    method, url, headers=headers, json=body,
                    timeout=aiohttp.ClientTimeout(total=180),
                ) as response:
                    payload = await _read_json(response)
                    if response.status == 200:
                        return payload if isinstance(payload, dict) else {}

                    error = GigaChatError(response.status, _error_message(payload))
                    # Токен мог протухнуть раньше срока — один раз пробуем обновить.
                    if error.is_auth_error and not refreshed:
                        refreshed = True
                        continue
                    if not error.is_retriable or attempt == self._retries - 1:
                        raise error
                    log.warning("GigaChat %s -> %s, повтор через %.1fs", path, response.status, delay)
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt == self._retries - 1:
                    raise GigaChatNetworkError(f"{method} {path}: {exc}") from exc
                log.warning("GigaChat недоступен (%s), повтор через %.1fs", exc, delay)

            await asyncio.sleep(delay)
            delay = min(delay * 2, 20.0)

        raise GigaChatNetworkError(f"{method} {path}: превышено число попыток")


async def _read_json(response: aiohttp.ClientResponse) -> Any:
    try:
        return await response.json(content_type=None)
    except (aiohttp.ContentTypeError, ValueError):
        return {"message": (await response.text())[:500]}


def _error_message(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("message", "error_description", "error", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
    return ""
