import json
import time

import pytest

from maxbot.ai.gigachat import GigaChatClient, GigaChatError, GigaChatNetworkError, parse_expires_at


class FakeResponse:
    def __init__(self, status: int, payload):
        self.status = status
        self._payload = payload

    async def json(self, content_type=None):
        return self._payload

    async def text(self):
        return json.dumps(self._payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class FakeSession:
    """Подменяет aiohttp-сессию: отдаёт заранее заготовленные ответы и пишет запросы."""

    def __init__(self, oauth=None, api=None):
        self.oauth = list(oauth or [])
        self.api = list(api or [])
        self.oauth_calls = []
        self.api_calls = []

    def post(self, url, *, headers=None, data=None, timeout=None):
        self.oauth_calls.append({"url": url, "headers": headers, "data": data})
        return self.oauth.pop(0) if self.oauth else FakeResponse(500, {})

    def request(self, method, url, *, headers=None, json=None, timeout=None):
        self.api_calls.append({"method": method, "url": url, "headers": headers, "body": json})
        return self.api.pop(0) if self.api else FakeResponse(500, {})


def token_response(token="tok", expires_in=1800):
    return FakeResponse(200, {"access_token": token, "expires_at": int(time.time() + expires_in)})


def chat_response(text="ответ"):
    return FakeResponse(200, {"choices": [{"message": {"role": "assistant", "content": text}, "index": 0}]})


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_seconds):
        return None

    monkeypatch.setattr("maxbot.ai.gigachat.asyncio.sleep", instant)


def test_parse_expires_at_handles_seconds_and_milliseconds():
    assert parse_expires_at(1679471442) == pytest.approx(1679471442)
    assert parse_expires_at(1679471442000) == pytest.approx(1679471442)


def test_parse_expires_at_falls_back_when_missing():
    assert parse_expires_at(None) > time.time()


async def test_token_request_uses_basic_auth_and_scope():
    session = FakeSession(oauth=[token_response("abc")])
    client = GigaChatClient("key123", scope="GIGACHAT_API_PERS", session=session)

    assert await client.access_token() == "abc"
    call = session.oauth_calls[0]
    assert call["url"].endswith("/api/v2/oauth")
    assert call["headers"]["Authorization"] == "Basic key123"
    assert call["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    assert call["data"] == {"scope": "GIGACHAT_API_PERS"}
    assert len(call["headers"]["RqUID"]) == 36


async def test_token_is_cached_between_calls():
    session = FakeSession(oauth=[token_response("abc")])
    client = GigaChatClient("key", session=session)

    await client.access_token()
    await client.access_token()
    assert len(session.oauth_calls) == 1


async def test_expired_token_is_refreshed():
    session = FakeSession(oauth=[token_response("old", expires_in=-10), token_response("new")])
    client = GigaChatClient("key", session=session)

    assert await client.access_token() == "old"
    assert await client.access_token() == "new"
    assert len(session.oauth_calls) == 2


async def test_bad_auth_key_raises():
    session = FakeSession(oauth=[FakeResponse(401, {"message": "Unauthorized"})])
    client = GigaChatClient("bad", session=session)

    with pytest.raises(GigaChatError) as info:
        await client.access_token()
    assert info.value.is_auth_error


async def test_chat_sends_bearer_token_and_returns_text():
    session = FakeSession(oauth=[token_response("tok")], api=[chat_response("Привет")])
    client = GigaChatClient("key", model="GigaChat", session=session)

    answer = await client.chat([{"role": "user", "content": "привет"}], max_tokens=100)

    assert answer == "Привет"
    call = session.api_calls[0]
    assert call["url"].endswith("/chat/completions")
    assert call["headers"]["Authorization"] == "Bearer tok"
    assert call["body"]["model"] == "GigaChat"
    assert call["body"]["max_tokens"] == 100
    assert call["body"]["messages"] == [{"role": "user", "content": "привет"}]


async def test_chat_passes_response_format():
    session = FakeSession(oauth=[token_response()], api=[chat_response("{}")])
    client = GigaChatClient("key", session=session)
    schema = {"type": "object", "properties": {}}

    await client.chat([{"role": "user", "content": "x"}], response_format={"type": "json_schema", "schema": schema})

    assert session.api_calls[0]["body"]["response_format"]["schema"] == schema


async def test_chat_refreshes_token_once_on_401():
    session = FakeSession(
        oauth=[token_response("stale"), token_response("fresh")],
        api=[FakeResponse(401, {"message": "expired"}), chat_response("готово")],
    )
    client = GigaChatClient("key", session=session)

    assert await client.chat([{"role": "user", "content": "x"}]) == "готово"
    assert len(session.oauth_calls) == 2
    assert session.api_calls[1]["headers"]["Authorization"] == "Bearer fresh"


async def test_chat_retries_on_rate_limit():
    session = FakeSession(
        oauth=[token_response()],
        api=[FakeResponse(429, {"message": "too many"}), chat_response("ок")],
    )
    client = GigaChatClient("key", session=session)

    assert await client.chat([{"role": "user", "content": "x"}]) == "ок"
    assert len(session.api_calls) == 2


async def test_chat_gives_up_after_retries():
    session = FakeSession(
        oauth=[token_response()],
        api=[FakeResponse(500, {"message": "boom"}) for _ in range(3)],
    )
    client = GigaChatClient("key", session=session, retries=3)

    with pytest.raises(GigaChatError):
        await client.chat([{"role": "user", "content": "x"}])


async def test_client_error_is_not_retried():
    session = FakeSession(oauth=[token_response()], api=[FakeResponse(400, {"message": "bad"})])
    client = GigaChatClient("key", session=session)

    with pytest.raises(GigaChatError) as info:
        await client.chat([{"role": "user", "content": "x"}])
    assert info.value.status == 400
    assert len(session.api_calls) == 1


async def test_empty_choices_returns_empty_string():
    session = FakeSession(oauth=[token_response()], api=[FakeResponse(200, {"choices": []})])
    client = GigaChatClient("key", session=session)

    assert await client.chat([{"role": "user", "content": "x"}]) == ""


async def test_network_failure_surfaces_as_network_error():
    class BrokenSession(FakeSession):
        def post(self, *args, **kwargs):
            raise __import__("aiohttp").ClientError("нет сети")

    client = GigaChatClient("key", session=BrokenSession())
    with pytest.raises(GigaChatNetworkError):
        await client.access_token()
