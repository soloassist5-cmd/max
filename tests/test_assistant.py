import pytest

from maxbot.ai.assistant import (
    Assistant,
    AssistantDisabled,
    BadModelAnswer,
    build_quiz,
    build_review,
    describe_error,
    extract_json,
)
from maxbot.ai.gigachat import GigaChatError, GigaChatNetworkError


class StubClient:
    """Отдаёт заранее заданный ответ вместо похода в GigaChat."""

    def __init__(self, answer: str):
        self.answer = answer
        self.calls = []

    async def chat(self, messages, **kwargs):
        self.calls.append({"messages": list(messages), **kwargs})
        return self.answer

    async def close(self):
        return None


QUIZ_JSON = """
{"questions": [
  {"question": "Что такое фотосинтез?", "options": ["Дыхание", "Питание светом", "Рост", "Сон"],
   "correct_index": 1, "explanation": "Растения производят глюкозу на свету."},
  {"question": "Где он идёт?", "options": ["В корне", "В листе", "В цветке", "В плоде"],
   "correct_index": 1, "explanation": "В хлоропластах листа."}
]}
"""


def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_from_code_fence():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_with_surrounding_text():
    assert extract_json('Вот ответ: {"a": 1} надеюсь помог') == {"a": 1}


def test_extract_json_rejects_garbage():
    with pytest.raises(BadModelAnswer):
        extract_json("никакого json тут нет")


def test_extract_json_rejects_array():
    with pytest.raises(BadModelAnswer):
        extract_json("[1, 2, 3]")


def test_build_quiz_parses_questions():
    quiz = build_quiz("Фотосинтез", extract_json(QUIZ_JSON))
    assert len(quiz) == 2
    assert quiz.topic == "Фотосинтез"
    assert quiz.questions[0].correct_option == "Питание светом"


def test_build_quiz_drops_questions_with_bad_index():
    payload = {
        "questions": [
            {"question": "ок", "options": ["а", "б"], "correct_index": 0, "explanation": ""},
            {"question": "плохой", "options": ["а", "б"], "correct_index": 7, "explanation": ""},
            {"question": "мало вариантов", "options": ["а"], "correct_index": 0, "explanation": ""},
            {"question": "", "options": ["а", "б"], "correct_index": 0, "explanation": ""},
        ]
    }
    quiz = build_quiz("тема", payload)
    assert [q.question for q in quiz.questions] == ["ок"]


def test_build_quiz_limits_question_count():
    payload = {
        "questions": [
            {"question": f"в{i}", "options": ["а", "б"], "correct_index": 0, "explanation": ""}
            for i in range(20)
        ]
    }
    assert len(build_quiz("тема", payload)) == 8


def test_build_quiz_without_valid_questions_raises():
    with pytest.raises(BadModelAnswer):
        build_quiz("тема", {"questions": []})


def test_build_quiz_without_list_raises():
    with pytest.raises(BadModelAnswer):
        build_quiz("тема", {"questions": "нет"})


def test_build_review_clamps_score():
    assert build_review({"score": 9, "correct": [], "mistakes": [], "advice": ""}).score == 5
    assert build_review({"score": -3, "correct": [], "mistakes": [], "advice": ""}).score == 1


def test_build_review_accepts_string_score():
    assert build_review({"score": "4", "correct": [], "mistakes": [], "advice": ""}).score == 4


def test_build_review_cleans_lists():
    review = build_review(
        {"score": 4, "correct": ["всё верно", "", 5], "mistakes": "не список", "advice": " учи правила "}
    )
    assert review.correct == ["всё верно"]
    assert review.mistakes == []
    assert review.advice == "учи правила"


def test_describe_error_covers_known_cases():
    assert "GIGACHAT_AUTH_KEY" in describe_error(AssistantDisabled())
    assert "формат" in describe_error(BadModelAnswer())
    assert "администратору" in describe_error(GigaChatError(401)).lower()
    assert "минуту" in describe_error(GigaChatError(429))
    assert "сократить" in describe_error(GigaChatError(422))
    assert "GigaChat" in describe_error(GigaChatNetworkError("нет сети"))
    assert describe_error(ValueError("что-то"))


async def test_assistant_disabled_without_client():
    assistant = Assistant(None)
    assert assistant.enabled is False
    with pytest.raises(AssistantDisabled):
        await assistant.ask("вопрос")


async def test_assistant_ask_builds_system_prompt_first():
    client = StubClient("Фотосинтез — это...")
    assistant = Assistant(client)

    answer = await assistant.ask("что такое фотосинтез")

    assert answer == "Фотосинтез — это..."
    messages = client.calls[0]["messages"]
    assert messages[0]["role"] == "system"
    assert [m["role"] for m in messages].count("system") == 1
    assert messages[1]["content"] == "что такое фотосинтез"


async def test_assistant_ask_returns_fallback_on_empty_answer():
    assistant = Assistant(StubClient(""))
    assert "попробуй" in (await assistant.ask("вопрос")).lower()


async def test_assistant_make_quiz_requests_json_schema():
    client = StubClient(QUIZ_JSON)
    quiz = await Assistant(client).make_quiz("Фотосинтез", count=2)

    assert len(quiz) == 2
    assert client.calls[0]["response_format"]["type"] == "json_schema"
    assert client.calls[0]["response_format"]["strict"] is True


async def test_assistant_make_quiz_clamps_count_into_prompt():
    client = StubClient(QUIZ_JSON)
    await Assistant(client).make_quiz("тема", count=99)
    assert "8 вопросов" in client.calls[0]["messages"][1]["content"]


async def test_assistant_review_parses_feedback():
    client = StubClient('{"score": 4, "correct": ["верно решено"], "mistakes": ["описка"], "advice": "проверяй"}')
    review = await Assistant(client).review("Алгебра", "решить уравнение", "x = 2")

    assert review.score == 4
    assert review.correct == ["верно решено"]
    assert review.advice == "проверяй"


async def test_assistant_search_without_materials_skips_request():
    client = StubClient("не должно вызваться")
    answer = await Assistant(client).search("что задали", "   ")

    assert client.calls == []
    assert "нечего искать" in answer


async def test_assistant_search_passes_materials():
    client = StubClient("Контрольная в пятницу")
    answer = await Assistant(client).search("когда контрольная", "Контрольные:\n#1 Химия — пятница")

    assert answer == "Контрольная в пятницу"
    assert "Химия" in client.calls[0]["messages"][1]["content"]
