from __future__ import annotations

import asyncio
import logging
import ssl
import time
from typing import Any, Mapping, Sequence

import aiohttp

from .errors import MaxApiError, MaxNetworkError
from .types import SUBSCRIBED_UPDATE_TYPES, BotInfo, Update

log = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 4000
MIN_INTERVAL_PER_CHAT = 0.5  # не больше 2 сообщений/сек в чат
GLOBAL_RPS = 30
DEFAULT_RETRIES = 4


class _RateLimiter:
    def __init__(self, rps: int) -> None:
        self._interval = 1.0 / rps
        self._lock = asyncio.Lock()
        self._next_at = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._next_at - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()
            self._next_at = now + self._interval


class _ChatThrottle:
    def __init__(self, min_interval: float = MIN_INTERVAL_PER_CHAT) -> None:
        self._min_interval = min_interval
        self._locks: dict[int, asyncio.Lock] = {}
        self._last_sent: dict[int, float] = {}

    async def acquire(self, key: int | None) -> None:
        if key is None:
            return
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            wait = self._last_sent.get(key, 0.0) + self._min_interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_sent[key] = time.monotonic()


def split_text(text: str, limit: int = MAX_TEXT_LENGTH) -> list[str]:
    """Режет текст на части не длиннее limit, стараясь не рвать строки."""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit:
            parts.append(current)
            current = line
        else:
            current += line
    if current or not parts:
        parts.append(current)
    return [part.rstrip("\n") or "⁣" for part in parts]


class MaxClient:
    def __init__(
        self,
        token: str,
        *,
        api_base: str = "https://platform-api2.max.ru",
        ca_bundle: str | None = None,
        session: aiohttp.ClientSession | None = None,
        retries: int = DEFAULT_RETRIES,
    ) -> None:
        self._token = token
        self._api_base = api_base.rstrip("/")
        self._ca_bundle = ca_bundle
        self._session = session
        self._owns_session = session is None
        self._retries = retries
        self._limiter = _RateLimiter(GLOBAL_RPS)
        self._throttle = _ChatThrottle()

    async def __aenter__(self) -> "MaxClient":
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def start(self) -> None:
        if self._session is not None:
            return
        ssl_context: ssl.SSLContext | None = None
        if self._ca_bundle:
            ssl_context = ssl.create_default_context(cafile=self._ca_bundle)
        connector = aiohttp.TCPConnector(ssl=ssl_context) if ssl_context else None
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=15, sock_read=120),
        )
        self._owns_session = True

    async def close(self) -> None:
        if self._session is not None and self._owns_session:
            await self._session.close()
        self._session = None

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        timeout: float | None = None,
    ) -> Any:
        if self._session is None:
            await self.start()
        assert self._session is not None

        url = f"{self._api_base}{path}"
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        headers = {"Authorization": self._token}
        request_timeout = aiohttp.ClientTimeout(total=timeout) if timeout is not None else None

        last_error: Exception | None = None
        for attempt in range(self._retries):
            await self._limiter.acquire()
            try:
                async with self._session.request(
                    method, url, params=clean_params, json=json,
                    headers=headers, timeout=request_timeout,
                ) as response:
                    payload = await self._read_payload(response)
                    if response.status == 200:
                        return payload
                    error = _build_error(response.status, payload)
                    if not error.is_retriable or attempt == self._retries - 1:
                        raise error
                    delay = _retry_delay(response.headers.get("Retry-After"), attempt)
                    log.warning("MAX API %s %s -> %s, повтор через %.1fs", method, path, response.status, delay)
                    last_error = error
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt == self._retries - 1:
                    raise MaxNetworkError(f"{method} {path}: {exc}") from exc
                delay = _retry_delay(None, attempt)
                log.warning("сеть недоступна (%s), повтор через %.1fs", exc, delay)
                last_error = exc
            await asyncio.sleep(delay)

        raise MaxNetworkError(f"{method} {path} не удался: {last_error}")

    @staticmethod
    async def _read_payload(response: aiohttp.ClientResponse) -> Any:
        try:
            return await response.json(content_type=None)
        except (aiohttp.ContentTypeError, ValueError):
            return {"message": (await response.text())[:500]}

    async def get_me(self) -> BotInfo:
        return BotInfo.parse(await self.request("GET", "/me"))

    async def set_commands(self, commands: Sequence[Mapping[str, str]]) -> Any:
        return await self.request("PATCH", "/me/commands", json={"commands": list(commands)})

    async def get_updates(
        self,
        *,
        marker: int | None = None,
        limit: int = 100,
        timeout: int = 30,
        types: Sequence[str] = SUBSCRIBED_UPDATE_TYPES,
    ) -> tuple[list[Update], int | None]:
        data = await self.request(
            "GET", "/updates",
            params={
                "marker": marker,
                "limit": limit,
                "timeout": timeout,
                "types": ",".join(types) if types else None,
            },
            timeout=timeout + 30,
        )
        updates = [Update.parse(item) for item in (data.get("updates") or []) if isinstance(item, dict)]
        return updates, data.get("marker")

    async def send_message(
        self,
        text: str,
        *,
        user_id: int | None = None,
        chat_id: int | None = None,
        attachments: Sequence[Mapping[str, Any]] | None = None,
        fmt: str | None = None,
        notify: bool = True,
        disable_link_preview: bool = False,
    ) -> dict[str, Any]:
        if user_id is None and chat_id is None:
            raise ValueError("нужен user_id или chat_id")

        chunks = split_text(text)
        result: dict[str, Any] = {}
        for index, chunk in enumerate(chunks):
            body: dict[str, Any] = {"text": chunk, "notify": notify}
            if fmt:
                body["format"] = fmt
            if attachments and index == len(chunks) - 1:
                body["attachments"] = list(attachments)
            await self._throttle.acquire(chat_id if chat_id is not None else user_id)
            result = await self.request(
                "POST", "/messages",
                params={
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "disable_link_preview": "true" if disable_link_preview else None,
                },
                json=body,
            )
        return result

    async def edit_message(
        self,
        message_id: str,
        text: str,
        *,
        attachments: Sequence[Mapping[str, Any]] | None = None,
        fmt: str | None = None,
    ) -> Any:
        body: dict[str, Any] = {"text": text[:MAX_TEXT_LENGTH], "attachments": list(attachments) if attachments else []}
        if fmt:
            body["format"] = fmt
        return await self.request("PUT", "/messages", params={"message_id": message_id}, json=body)

    async def answer_callback(
        self,
        callback_id: str,
        *,
        text: str | None = None,
        attachments: Sequence[Mapping[str, Any]] | None = None,
        notification: str | None = None,
        fmt: str | None = None,
    ) -> Any:
        body: dict[str, Any] = {}
        if notification:
            body["notification"] = notification[:200]
        if text is not None:
            msg: dict[str, Any] = {"text": text[:MAX_TEXT_LENGTH], "attachments": list(attachments) if attachments else []}
            if fmt:
                msg["format"] = fmt
            body["message"] = msg
        return await self.request("POST", "/answers", params={"callback_id": callback_id}, json=body)

    async def send_action(self, chat_id: int, action: str = "typing_on") -> Any:
        return await self.request("POST", f"/chats/{chat_id}/actions", json={"action": action})

    async def subscribe(self, url: str, types: Sequence[str] = SUBSCRIBED_UPDATE_TYPES) -> Any:
        return await self.request("POST", "/subscriptions", json={"url": url, "update_types": list(types)})

    async def unsubscribe(self, url: str) -> Any:
        return await self.request("DELETE", "/subscriptions", params={"url": url})

    async def get_subscriptions(self) -> Any:
        return await self.request("GET", "/subscriptions")


def _build_error(status: int, payload: Any) -> MaxApiError:
    code = ""
    message = ""
    if isinstance(payload, dict):
        code = str(payload.get("code") or "")
        message = str(payload.get("message") or "")
    return MaxApiError(status, code, message)


def _retry_delay(retry_after: str | None, attempt: int) -> float:
    if retry_after:
        try:
            return min(float(retry_after), 60.0)
        except ValueError:
            pass
    return min(2.0**attempt, 30.0)
