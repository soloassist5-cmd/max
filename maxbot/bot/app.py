from __future__ import annotations

import asyncio
import logging

from ..ai import Assistant
from ..ai.gigachat import GigaChatClient
from ..api.client import MaxClient
from ..api.errors import MaxApiError, MaxNetworkError
from ..api.types import Update
from ..config import Config, ConfigError
from ..storage import Storage
from .context import Context
from .handlers import ai as ai_handlers
from .handlers import common, events, grades, homework, schedule, settings
from .router import Router

log = logging.getLogger(__name__)

BOT_COMMANDS = [
    {"name": "start", "description": "Начать работу с ботом"},
    {"name": "help", "description": "Список команд"},
    {"name": "today", "description": "Расписание и дела на сегодня"},
    {"name": "tomorrow", "description": "Расписание и дела на завтра"},
    {"name": "week", "description": "Расписание на неделю"},
    {"name": "bells", "description": "Расписание звонков"},
    {"name": "homework", "description": "Домашние задания"},
    {"name": "grades", "description": "Оценки"},
    {"name": "events", "description": "Контрольные и дедлайны"},
    {"name": "ask", "description": "Спросить ИИ-помощника"},
    {"name": "quiz", "description": "Тест по теме урока"},
    {"name": "check", "description": "Проверить своё задание"},
    {"name": "find", "description": "Поиск по материалам класса"},
    {"name": "menu", "description": "Главное меню"},
]


def build_router() -> Router:
    router = Router()
    common.register(router)
    schedule.register(router)
    homework.register(router)
    grades.register(router)
    events.register(router)
    settings.register(router)
    ai_handlers.register(router)
    return router


class App:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.client = MaxClient(config.token, api_base=config.api_base, ca_bundle=config.ca_bundle)
        self.storage = Storage(config.database_path, default_tz_offset=config.default_tz_offset)
        self.ai = Assistant(_build_gigachat(config))
        self.router = build_router()

    async def start(self) -> None:
        await self.client.start()
        await self.storage.connect()
        await self.check_token()
        if not self.ai.enabled:
            log.warning("GIGACHAT_AUTH_KEY не задан — ИИ-функции будут отключены")
        try:
            await self.client.set_commands(BOT_COMMANDS)
        except Exception:
            log.exception("не удалось обновить список команд бота")

    async def check_token(self) -> None:
        """Проверяет токен до запуска: с неверным токеном бот не должен молча крутиться."""
        try:
            info = await self.client.get_me()
        except MaxApiError as exc:
            if exc.is_auth_error:
                raise ConfigError(
                    "MAX_BOT_TOKEN отклонён сервером MAX. Проверьте, что скопировали токен "
                    "целиком и из настроек нужного бота."
                ) from exc
            log.warning("не удалось получить данные бота: %s", exc)
            return
        except MaxNetworkError as exc:
            log.warning("MAX API сейчас недоступен (%s), продолжаем запуск", exc)
            return
        log.info("токен принят: бот «%s» (@%s)", info.name, info.username or "без никнейма")

    async def stop(self) -> None:
        await self.ai.close()
        await self.storage.close()
        await self.client.close()

    async def handle_update(self, update: Update) -> None:
        try:
            await self._handle_update(update)
        except Exception:
            log.exception("ошибка при обработке события %s", update.type)

    async def _handle_update(self, update: Update) -> None:
        target_id = update.user_id if update.is_dialog else update.chat_id
        if target_id is None:
            return

        chat_type = update.effective_chat_type
        if chat_type:
            await self.storage.touch_chat(target_id, chat_type=chat_type)
        chat_settings = await self.storage.get_chat_settings(target_id)

        ctx = Context(
            client=self.client,
            storage=self.storage,
            config=self.config,
            update=update,
            user=update.user,
            chat_id=target_id,
            reply_kind="user_id" if update.is_dialog else "chat_id",
            tz_offset=chat_settings.tz_offset,
            ai=self.ai,
        )
        await self.router.dispatch(ctx)

    async def run_polling(self) -> None:
        marker = await self.storage.get_marker()
        log.info("бот запущен в режиме polling")
        while True:
            try:
                updates, marker = await self.client.get_updates(
                    marker=marker, limit=self.config.poll_limit, timeout=self.config.poll_timeout,
                )
            except MaxApiError as exc:
                if exc.is_auth_error:
                    raise ConfigError("MAX_BOT_TOKEN больше не действует — бот остановлен.") from exc
                log.exception("ошибка long polling, повтор через 5 секунд")
                await asyncio.sleep(5)
                continue
            except Exception:
                log.exception("ошибка long polling, повтор через 5 секунд")
                await asyncio.sleep(5)
                continue
            for update in updates:
                await self.handle_update(update)
            if marker is not None:
                await self.storage.set_marker(marker)


def _build_gigachat(config: Config) -> GigaChatClient | None:
    if not config.ai_enabled:
        return None
    return GigaChatClient(
        config.gigachat_auth_key,
        scope=config.gigachat_scope,
        model=config.gigachat_model,
        ca_bundle=config.gigachat_ca_bundle,
        verify_ssl=config.gigachat_verify_ssl,
    )
