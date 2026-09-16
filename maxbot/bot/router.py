from __future__ import annotations

from typing import Awaitable, Callable

from ..api.types import BOT_STARTED, MESSAGE_CALLBACK, MESSAGE_CREATED
from .context import Context

CommandHandler = Callable[[Context, str], Awaitable[None]]
CallbackHandler = Callable[[Context, list[str]], Awaitable[None]]
FlowHandler = Callable[[Context, str, dict], Awaitable[None]]

CANCEL_WORDS = {"отмена", "cancel", "стоп", "/cancel"}


class Router:
    def __init__(self) -> None:
        self._commands: dict[str, CommandHandler] = {}
        self._callbacks: dict[str, CallbackHandler] = {}
        self._flows: dict[str, FlowHandler] = {}

    def command(self, *names: str) -> Callable[[CommandHandler], CommandHandler]:
        def wrap(handler: CommandHandler) -> CommandHandler:
            for name in names:
                self._commands[name] = handler
            return handler
        return wrap

    def callback(self, prefix: str) -> Callable[[CallbackHandler], CallbackHandler]:
        def wrap(handler: CallbackHandler) -> CallbackHandler:
            self._callbacks[prefix] = handler
            return handler
        return wrap

    def flow(self, action: str) -> Callable[[FlowHandler], FlowHandler]:
        def wrap(handler: FlowHandler) -> FlowHandler:
            self._flows[action] = handler
            return handler
        return wrap

    async def dispatch(self, ctx: Context) -> None:
        update = ctx.update

        if update.type == MESSAGE_CALLBACK:
            await self._dispatch_callback(ctx)
            return

        if update.type == BOT_STARTED:
            handler = self._commands.get("/start")
            if handler:
                await handler(ctx, "")
            return

        if update.type != MESSAGE_CREATED:
            return

        text = update.text
        if not text:
            return

        if ctx.user_id is not None and text.strip().lower() in CANCEL_WORDS:
            if await ctx.storage.get_pending(ctx.chat_id, ctx.user_id):
                await ctx.clear_pending()
                await ctx.reply("Отменила. Что дальше?")
            return

        if text.startswith("/"):
            command = text.split()[0].split("@")[0].lower()
            args = text[len(command):].strip()
            handler = self._commands.get(command)
            if handler is None:
                await ctx.reply("Такой команды не знаю. Наберите /help.")
                return
            await ctx.clear_pending()
            await handler(ctx, args)
            return

        pending = await ctx.storage.get_pending(ctx.chat_id, ctx.user_id) if ctx.user_id is not None else None
        if pending:
            action, data = pending
            handler = self._flows.get(action)
            if handler:
                await handler(ctx, text.strip(), data)
            return

        if update.is_dialog:
            await ctx.reply("Не поняла 🤔 Наберите /help, чтобы увидеть список команд.")

    async def _dispatch_callback(self, ctx: Context) -> None:
        prefix, _, rest = ctx.update.payload.partition(":")
        handler = self._callbacks.get(prefix)
        if handler is None:
            await ctx.toast("Кнопка устарела")
            return
        await handler(ctx, rest.split(":") if rest else [])
