from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from ..api.client import MaxClient
from ..api.types import MESSAGE_CALLBACK, Update, User
from ..config import Config
from ..domain import dates as dt
from ..storage import Storage


@dataclass
class Context:
    client: MaxClient
    storage: Storage
    config: Config
    update: Update
    user: User | None
    chat_id: int
    reply_kind: str  # "chat_id" либо "user_id"
    tz_offset: int

    @property
    def user_id(self) -> int | None:
        return self.user.user_id if self.user else None

    @property
    def today(self) -> date:
        return dt.today(self.tz_offset)

    def _target(self) -> dict[str, int]:
        return {self.reply_kind: self.chat_id}

    async def reply(
        self, text: str, *, keyboard: dict[str, Any] | None = None, fmt: str | None = None, notify: bool = True,
    ) -> None:
        attachments = [keyboard] if keyboard else None
        await self.client.send_message(text, attachments=attachments, fmt=fmt, notify=notify, **self._target())

    async def answer(
        self, *, text: str | None = None, keyboard: dict[str, Any] | None = None,
        notification: str | None = None, fmt: str | None = None,
    ) -> None:
        if not self.update.callback_id:
            return
        attachments = [keyboard] if keyboard else None
        await self.client.answer_callback(
            self.update.callback_id, text=text, attachments=attachments, notification=notification, fmt=fmt,
        )

    async def show(self, text: str, *, keyboard: dict[str, Any] | None = None, fmt: str | None = None) -> None:
        """Отвечает на кнопку правкой сообщения либо отправляет новое — смотря что вызвало обработчик."""
        if self.update.type == MESSAGE_CALLBACK:
            await self.answer(text=text, keyboard=keyboard, fmt=fmt)
        else:
            await self.reply(text, keyboard=keyboard, fmt=fmt)

    async def toast(self, text: str) -> None:
        await self.answer(notification=text)

    async def set_pending(self, action: str, data: dict[str, Any] | None = None) -> None:
        if self.user_id is not None:
            await self.storage.set_pending(self.chat_id, self.user_id, action, data)

    async def clear_pending(self) -> None:
        if self.user_id is not None:
            await self.storage.clear_pending(self.chat_id, self.user_id)
