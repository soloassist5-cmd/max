from __future__ import annotations

import asyncio
import logging
import signal
import sys

from .bot.app import App
from .bot.scheduler import Scheduler
from .config import Config, ConfigError


def _setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


async def _run(config: Config) -> None:
    app = App(config)
    await app.start()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:
                pass  # не на всех платформах (например, Windows) можно повесить обработчик сигнала

    scheduler = Scheduler(app.client, app.storage, config)
    tasks = [asyncio.create_task(scheduler.run())]
    if config.mode == "webhook":
        from .bot.webhook import run_webhook

        tasks.append(asyncio.create_task(run_webhook(app)))
    else:
        tasks.append(asyncio.create_task(app.run_polling()))

    try:
        await stop_event.wait()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await app.stop()


def main() -> None:
    _setup_logging()
    try:
        config = Config.from_env()
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        raise SystemExit(1)
    try:
        asyncio.run(_run(config))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
