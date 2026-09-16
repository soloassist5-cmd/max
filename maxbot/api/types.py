from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

MESSAGE_CREATED = "message_created"
MESSAGE_CALLBACK = "message_callback"
MESSAGE_EDITED = "message_edited"
MESSAGE_REMOVED = "message_removed"
BOT_STARTED = "bot_started"
BOT_ADDED = "bot_added"
BOT_REMOVED = "bot_removed"
BOT_STOPPED = "bot_stopped"
USER_ADDED = "user_added"
USER_REMOVED = "user_removed"
CHAT_TITLE_CHANGED = "chat_title_changed"
DIALOG_REMOVED = "dialog_removed"
DIALOG_CLEARED = "dialog_cleared"

SUBSCRIBED_UPDATE_TYPES = (
    MESSAGE_CREATED,
    MESSAGE_CALLBACK,
    BOT_STARTED,
    BOT_ADDED,
    BOT_REMOVED,
)

CHAT_TYPE_DIALOG = "dialog"
CHAT_TYPE_CHAT = "chat"
CHAT_TYPE_CHANNEL = "channel"


@dataclass(frozen=True, slots=True)
class User:
    user_id: int
    name: str
    username: str | None = None
    is_bot: bool = False

    @classmethod
    def parse(cls, data: Mapping[str, Any] | None) -> "User | None":
        if not data or data.get("user_id") is None:
            return None
        return cls(
            user_id=int(data["user_id"]),
            name=(data.get("name") or "").strip(),
            username=data.get("username") or None,
            is_bot=bool(data.get("is_bot", False)),
        )

    @property
    def first_name(self) -> str:
        return self.name.split()[0] if self.name.strip() else "друг"


@dataclass(frozen=True, slots=True)
class Update:
    type: str
    timestamp: int
    raw: dict[str, Any]

    @classmethod
    def parse(cls, data: Mapping[str, Any]) -> "Update":
        return cls(
            type=str(data.get("update_type", "")),
            timestamp=int(data.get("timestamp") or 0),
            raw=dict(data),
        )

    @property
    def message(self) -> dict[str, Any] | None:
        message = self.raw.get("message")
        return message if isinstance(message, dict) else None

    @property
    def message_id(self) -> str | None:
        message = self.message
        if not message:
            return None
        body = message.get("body")
        return body.get("mid") if isinstance(body, dict) else None

    @property
    def text(self) -> str:
        message = self.message
        body = message.get("body") if message else None
        if not isinstance(body, dict):
            return ""
        return (body.get("text") or "").strip()

    @property
    def attachments(self) -> list[dict[str, Any]]:
        message = self.message
        body = message.get("body") if message else None
        if not isinstance(body, dict):
            return []
        return [item for item in (body.get("attachments") or []) if isinstance(item, dict)]

    @property
    def user(self) -> User | None:
        if self.type == MESSAGE_CALLBACK:
            callback = self.raw.get("callback")
            return User.parse(callback.get("user")) if isinstance(callback, dict) else None
        if "user" in self.raw:
            return User.parse(self.raw.get("user"))
        message = self.message
        return User.parse(message.get("sender")) if message else None

    @property
    def user_id(self) -> int | None:
        user = self.user
        return user.user_id if user else None

    @property
    def _recipient(self) -> dict[str, Any]:
        message = self.message
        recipient = message.get("recipient") if message else None
        return recipient if isinstance(recipient, dict) else {}

    @property
    def chat_id(self) -> int | None:
        direct = self.raw.get("chat_id")
        if direct is not None:
            return int(direct)
        chat_id = self._recipient.get("chat_id")
        return int(chat_id) if chat_id is not None else None

    @property
    def chat_type(self) -> str:
        return str(self._recipient.get("chat_type") or CHAT_TYPE_DIALOG)

    @property
    def is_dialog(self) -> bool:
        if self.type in (BOT_STARTED, BOT_STOPPED, DIALOG_REMOVED, DIALOG_CLEARED):
            return True
        if self.type in (BOT_ADDED, BOT_REMOVED):
            return False
        return self.chat_type == CHAT_TYPE_DIALOG

    @property
    def effective_chat_type(self) -> str | None:
        """Тип чата для тех событий, где его вообще можно определить."""
        if self.type in (BOT_STARTED, BOT_STOPPED, DIALOG_REMOVED, DIALOG_CLEARED):
            return CHAT_TYPE_DIALOG
        if self.type in (BOT_ADDED, BOT_REMOVED):
            return CHAT_TYPE_CHANNEL if self.raw.get("is_channel") else CHAT_TYPE_CHAT
        if self.type in (MESSAGE_CREATED, MESSAGE_CALLBACK, MESSAGE_EDITED, MESSAGE_REMOVED):
            return self.chat_type
        return None

    @property
    def callback_id(self) -> str | None:
        callback = self.raw.get("callback")
        return callback.get("callback_id") if isinstance(callback, dict) else None

    @property
    def payload(self) -> str:
        callback = self.raw.get("callback")
        if isinstance(callback, dict):
            return callback.get("payload") or ""
        return self.raw.get("payload") or ""


@dataclass(frozen=True, slots=True)
class BotInfo:
    user_id: int
    name: str
    username: str | None

    @classmethod
    def parse(cls, data: Mapping[str, Any]) -> "BotInfo":
        return cls(
            user_id=int(data.get("user_id") or 0),
            name=data.get("name") or "",
            username=data.get("username") or None,
        )
