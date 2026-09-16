from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from ..api.types import Update
from .app import App

log = logging.getLogger(__name__)


def create_web_app(app: App) -> web.Application:
    web_app = web.Application()

    async def handle(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except Exception:
            return web.Response(status=400, text="bad json")
        if not isinstance(payload, dict):
            return web.Response(status=400, text="bad payload")
        update = Update.parse(payload)
        # отвечаем сразу и обрабатываем в фоне — MAX не должен ждать нашу бизнес-логику
        asyncio.create_task(app.handle_update(update))
        return web.Response(status=200, text="ok")

    web_app.router.add_post(app.config.webhook_path, handle)
    return web_app


async def run_webhook(app: App) -> None:
    """Предполагает, что app.start() уже вызван."""
    await app.client.subscribe(app.config.webhook_url)
    web_app = create_web_app(app)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, app.config.webhook_host, app.config.webhook_port)
    await site.start()
    log.info("webhook слушает %s:%s%s", app.config.webhook_host, app.config.webhook_port, app.config.webhook_path)
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
