import asyncio

import pytest

from maxbot import __main__ as entrypoint
from maxbot.api.errors import MaxApiError, MaxNetworkError
from maxbot.api.types import BotInfo
from maxbot.bot.app import App
from maxbot.config import Config, ConfigError


@pytest.fixture
async def app(tmp_path):
    instance = App(Config(token="t", database_path=str(tmp_path / "startup.db")))
    await instance.client.start()
    await instance.storage.connect()
    yield instance
    await instance.stop()


async def test_check_token_rejects_bad_token(app):
    async def unauthorized():
        raise MaxApiError(401, "verify.token", "invalid token")

    app.client.get_me = unauthorized
    with pytest.raises(ConfigError, match="MAX_BOT_TOKEN"):
        await app.check_token()


async def test_check_token_survives_api_outage(app):
    async def offline():
        raise MaxNetworkError("сеть недоступна")

    app.client.get_me = offline
    await app.check_token()  # временная недоступность не должна мешать запуску


async def test_check_token_passes_on_valid_token(app):
    async def ok():
        return BotInfo(user_id=1, name="Школьный помощник", username="school_bot")

    app.client.get_me = ok
    await app.check_token()


async def test_polling_stops_when_token_revoked(app):
    async def unauthorized(**kwargs):
        raise MaxApiError(401, "verify.token", "invalid token")

    app.client.get_updates = unauthorized
    with pytest.raises(ConfigError):
        await app.run_polling()


async def test_polling_retries_on_temporary_error(app, monkeypatch):
    calls = []

    async def flaky(**kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise MaxApiError(503, "", "service unavailable")
        raise asyncio.CancelledError

    async def instant(_seconds):
        return None

    monkeypatch.setattr("maxbot.bot.app.asyncio.sleep", instant)
    app.client.get_updates = flaky
    with pytest.raises(asyncio.CancelledError):
        await app.run_polling()
    assert len(calls) == 2


async def test_run_exits_when_worker_task_fails(monkeypatch):
    """Упавшая рабочая задача должна останавливать процесс, а не подвешивать его."""

    class FakeApp:
        def __init__(self, config):
            self.config = config
            self.client = object()
            self.storage = object()
            self.stopped = False

        async def start(self):
            return None

        async def stop(self):
            self.stopped = True

        async def run_polling(self):
            raise ConfigError("токен отозван")

    class FakeScheduler:
        def __init__(self, *args):
            pass

        async def run(self):
            await asyncio.Event().wait()

    monkeypatch.setattr(entrypoint, "App", FakeApp)
    monkeypatch.setattr(entrypoint, "Scheduler", FakeScheduler)

    with pytest.raises(ConfigError, match="токен отозван"):
        await asyncio.wait_for(entrypoint._run(Config(token="t")), timeout=5)
