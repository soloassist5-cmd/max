import pytest

from maxbot.ai.assistant import Assistant
from maxbot.api.types import Update
from maxbot.bot.app import build_router
from maxbot.bot.context import Context
from maxbot.config import Config
from maxbot.storage import Storage

QUIZ_JSON = """
{"questions": [
  {"question": "Вопрос раз", "options": ["а", "б", "в", "г"], "correct_index": 1, "explanation": "Потому что б."},
  {"question": "Вопрос два", "options": ["а", "б", "в", "г"], "correct_index": 0, "explanation": "Потому что а."}
]}
"""


class FakeMaxClient:
    def __init__(self):
        self.sent = []
        self.answered = []

    async def send_message(self, text, **kwargs):
        self.sent.append(text)
        return {}

    async def answer_callback(self, callback_id, *, text=None, attachments=None, notification=None, fmt=None):
        self.answered.append({"text": text, "notification": notification, "attachments": attachments})
        return {}


class StubGiga:
    def __init__(self, answer=""):
        self.answer = answer
        self.calls = []

    async def chat(self, messages, **kwargs):
        self.calls.append(list(messages))
        return self.answer

    async def close(self):
        return None


def message_update(text, *, user_id=1, chat_id=100):
    return Update.parse({
        "update_type": "message_created",
        "timestamp": 0,
        "message": {
            "sender": {"user_id": user_id, "name": "Аня Иванова"},
            "recipient": {"chat_id": chat_id, "chat_type": "chat"},
            "body": {"mid": "m1", "seq": 1, "text": text},
        },
    })


def callback_update(payload, *, user_id=1, chat_id=100):
    return Update.parse({
        "update_type": "message_callback",
        "timestamp": 0,
        "callback": {"timestamp": 0, "callback_id": "cb", "payload": payload,
                     "user": {"user_id": user_id, "name": "Аня Иванова"}},
        "message": {"recipient": {"chat_id": chat_id, "chat_type": "chat"},
                    "body": {"mid": "m2", "seq": 2, "text": ""}},
    })


@pytest.fixture
async def bot(tmp_path):
    storage = Storage(str(tmp_path / "ai.db"))
    await storage.connect()
    client = FakeMaxClient()
    giga = StubGiga()
    assistant = Assistant(giga)
    router = build_router()
    config = Config(token="x")

    async def send(update):
        ctx = Context(
            client=client, storage=storage, config=config, update=update,
            user=update.user, chat_id=100, reply_kind="chat_id", tz_offset=3, ai=assistant,
        )
        await router.dispatch(ctx)

    yield {"send": send, "client": client, "giga": giga, "storage": storage, "assistant": assistant}
    await storage.close()


def last_text(bot) -> str:
    """Последнее, что бот показал пользователю, — сообщением или правкой по кнопке."""
    texts = list(bot["client"].sent) + [a["text"] for a in bot["client"].answered if a["text"]]
    return texts[-1] if texts else ""


async def test_ask_command_returns_model_answer(bot):
    bot["giga"].answer = "Фотосинтез — это питание растений светом."
    await bot["send"](message_update("/ask что такое фотосинтез"))

    assert "Фотосинтез — это питание растений светом." in bot["client"].sent


async def test_ask_without_arguments_asks_for_question(bot):
    await bot["send"](message_update("/ask"))
    assert "О чём спросить" in bot["client"].sent[-1]

    bot["giga"].answer = "Ответ на вопрос"
    await bot["send"](message_update("почему небо голубое"))
    assert "Ответ на вопрос" in bot["client"].sent


async def test_quiz_runs_through_questions_and_shows_result(bot):
    bot["giga"].answer = QUIZ_JSON
    await bot["send"](message_update("/quiz Фотосинтез"))

    assert "Вопрос 1 из 2" in last_text(bot)
    pending = await bot["storage"].get_pending(100, 1)
    assert pending[0] == "quiz_active"

    await bot["send"](callback_update("quiz:answer:1"))  # верный вариант
    feedback = last_text(bot)
    assert "Верно!" in feedback
    assert "Потому что б." in feedback
    assert "Счёт: 1 из 1" in feedback

    await bot["send"](callback_update("quiz:next"))
    assert "Вопрос 2 из 2" in last_text(bot)

    await bot["send"](callback_update("quiz:answer:3"))  # неверный вариант
    assert "Неверно. Правильный ответ: а" in last_text(bot)

    await bot["send"](callback_update("quiz:next"))
    result = last_text(bot)
    assert "Результат: 1 из 2" in result
    assert await bot["storage"].get_pending(100, 1) is None


async def test_quiz_stop_button_ends_early(bot):
    bot["giga"].answer = QUIZ_JSON
    await bot["send"](message_update("/quiz Дроби"))
    await bot["send"](callback_update("quiz:stop"))

    assert "Результат: 0 из 2" in last_text(bot)
    assert await bot["storage"].get_pending(100, 1) is None


async def test_text_during_quiz_points_back_to_buttons(bot):
    bot["giga"].answer = QUIZ_JSON
    await bot["send"](message_update("/quiz Дроби"))
    await bot["send"](message_update("наверное б"))

    assert "кнопкой" in bot["client"].sent[-1]
    assert (await bot["storage"].get_pending(100, 1))[0] == "quiz_active"


async def test_quiz_callback_after_finish_is_ignored(bot):
    await bot["send"](callback_update("quiz:answer:1"))
    assert bot["client"].answered[-1]["notification"] == "Тест уже завершён"


async def test_broken_model_answer_reports_friendly_error(bot):
    bot["giga"].answer = "я не умею в json"
    await bot["send"](message_update("/quiz Дроби"))

    assert "формате" in bot["client"].sent[-1]
    assert await bot["storage"].get_pending(100, 1) is None


async def test_check_flow_collects_work_and_returns_review(bot):
    await bot["send"](message_update("/check"))
    assert "предмету" in bot["client"].sent[-1]

    await bot["send"](message_update("Алгебра"))
    assert "задано" in bot["client"].sent[-1]

    await bot["send"](message_update("решить уравнение 2x = 4"))
    assert "работу" in bot["client"].sent[-1]

    bot["giga"].answer = (
        '{"score": 5, "correct": ["корень найден верно"], "mistakes": [], "advice": "записывай проверку"}'
    )
    await bot["send"](message_update("x = 2"))

    review = bot["client"].sent[-1]
    assert "Оценка за работу: 5 из 5" in review
    assert "+ корень найден верно" in review
    assert "Совет: записывай проверку" in review
    assert await bot["storage"].get_pending(100, 1) is None


async def test_find_uses_stored_materials_as_context(bot):
    await bot["storage"].upsert_lesson(100, weekday=0, slot=1, subject="Химия", room="204")
    bot["giga"].answer = "Химия в понедельник первым уроком."

    await bot["send"](message_update("/find когда химия"))

    assert "Химия в понедельник первым уроком." in bot["client"].sent
    materials = bot["giga"].calls[-1][1]["content"]
    assert "Химия" in materials


async def test_find_without_data_says_nothing_to_search(bot):
    await bot["send"](message_update("/find когда химия"))

    assert "нечего искать" in bot["client"].sent[-1]
    assert bot["giga"].calls == []


async def test_ai_commands_explain_setup_when_key_missing(bot):
    bot["assistant"]._client = None

    await bot["send"](message_update("/ask вопрос"))
    assert "GIGACHAT_AUTH_KEY" in bot["client"].sent[-1]


async def test_ai_menu_opens_section(bot):
    await bot["send"](callback_update("menu:ai"))
    assert "ИИ-помощник" in bot["client"].answered[-1]["text"]
