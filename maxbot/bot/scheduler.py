from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from ..api.client import MaxClient
from ..config import Config
from ..domain import bells as bells_domain
from ..domain import dates as dt
from ..domain import events as events_domain
from ..domain import schedule as schedule_domain
from ..storage import ChatSettings, Storage

log = logging.getLogger(__name__)

CHECK_INTERVAL = 60


def _target(chat: ChatSettings) -> dict[str, int]:
    return {"user_id": chat.chat_id} if chat.chat_type == "dialog" else {"chat_id": chat.chat_id}


class Scheduler:
    """Раз в минуту проверяет чаты и рассылает утренний/вечерний дайджест."""

    def __init__(self, client: MaxClient, storage: Storage, config: Config) -> None:
        self._client = client
        self._storage = storage
        self._config = config

    async def run(self) -> None:
        log.info("планировщик напоминаний запущен")
        while True:
            try:
                await self._tick()
            except Exception:
                log.exception("сбой в планировщике")
            await asyncio.sleep(CHECK_INTERVAL)

    async def _tick(self) -> None:
        if not self._config.reminders_enabled:
            return
        for chat in await self._storage.list_chats():
            if not chat.digest_enabled:
                continue
            try:
                await self._tick_chat(chat)
            except Exception:
                log.exception("не удалось отправить дайджест в чат %s", chat.chat_id)

    async def _tick_chat(self, chat: ChatSettings) -> None:
        now = dt.now(chat.tz_offset)
        hhmm = now.strftime("%H:%M")
        today_date = now.date()
        today_iso = today_date.isoformat()

        morning_at = chat.morning_digest_at or self._config.morning_digest_at
        if hhmm >= morning_at and chat.last_morning_digest != today_iso:
            await self._send_digest(chat, today_date, today_date)
            await self._storage.mark_digest_sent(chat.chat_id, kind="morning", iso_date=today_iso)

        evening_at = chat.evening_digest_at or self._config.evening_digest_at
        if hhmm >= evening_at and chat.last_evening_digest != today_iso:
            await self._send_digest(chat, today_date + timedelta(days=1), today_date, evening=True)
            await self._storage.mark_digest_sent(chat.chat_id, kind="evening", iso_date=today_iso)

    async def _send_digest(
        self, chat: ChatSettings, target_date: date, today_date: date, *, evening: bool = False,
    ) -> None:
        lessons = schedule_domain.by_weekday(await self._storage.list_lessons(chat.chat_id), target_date.weekday())
        bells = await self._storage.get_bells(chat.chat_id) or list(bells_domain.DEFAULT_BELLS)
        homework = await self._storage.list_homework_by_date(chat.chat_id, target_date)
        reminders = await self._storage.events_to_remind(chat.chat_id, today_date, today_date + timedelta(days=1))

        if not lessons and not homework and not reminders:
            return  # нечего сказать — не будим людей просто так

        greeting = "Добрый вечер! Собираемся на завтра" if evening else "Доброе утро!"
        lines = [f"{greeting} {dt.format_date(target_date)}.", "", "Уроки:", schedule_domain.format_day(lessons, bells)]
        if homework:
            lines += ["", "Сдать:"] + [f"• {item.subject} — {item.text}" for item in homework]
        if reminders:
            lines += ["", "Не забыть:"] + [
                f"• {events_domain.format_event(event, today_date=target_date)}" for event in reminders
            ]

        await self._client.send_message("\n".join(lines), **_target(chat))
        for event in reminders:
            await self._storage.mark_event_notified(event.id)
