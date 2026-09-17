from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .gigachat import GigaChatClient, GigaChatError, GigaChatNetworkError

MIN_QUIZ_QUESTIONS = 3
MAX_QUIZ_QUESTIONS = 8
MAX_OPTIONS = 4

QUIZ_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "description": "Список вопросов теста",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "Текст вопроса"},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ровно четыре варианта ответа",
                    },
                    "correct_index": {
                        "type": "integer",
                        "description": "Номер правильного варианта в массиве options, начиная с нуля",
                    },
                    "explanation": {
                        "type": "string",
                        "description": "Короткое пояснение, почему этот ответ правильный",
                    },
                },
                "required": ["question", "options", "correct_index", "explanation"],
            },
        }
    },
    "required": ["questions"],
}

REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "description": "Оценка работы по пятибалльной шкале, от 1 до 5"},
        "correct": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Что ученик сделал верно",
        },
        "mistakes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Ошибки и неточности, которые нужно исправить",
        },
        "advice": {"type": "string", "description": "Главный совет ученику одним предложением"},
    },
    "required": ["score", "correct", "mistakes", "advice"],
}

PLAIN_TEXT_RULE = (
    "Пиши обычным текстом без markdown-разметки: без звёздочек, решёток и таблиц. "
    "Для перечислений используй дефисы."
)

ASK_SYSTEM = (
    "Ты — помощник школьника в чат-боте. Объясняешь темы школьной программы простыми словами "
    "и с примерами. Если просят решить домашнее задание, сначала разбери ход решения, "
    "чтобы ученик понял, а не просто скопировал. Если вопрос не про учёбу и не про школу — "
    "вежливо скажи, что помогаешь с учёбой. Отвечай по-русски, не длиннее 2000 знаков. " + PLAIN_TEXT_RULE
)

QUIZ_SYSTEM = (
    "Ты составляешь проверочные тесты для школьников по школьной программе. "
    "Вопросы должны быть разными по сложности, с одним однозначно правильным вариантом "
    "и тремя правдоподобными неправильными."
)

REVIEW_SYSTEM = (
    "Ты — доброжелательный учитель. Проверяешь работу ученика: отмечаешь, что получилось, "
    "честно указываешь на ошибки и объясняешь, как их исправить. Не занижай и не завышай оценку. " + PLAIN_TEXT_RULE
)

SEARCH_SYSTEM = (
    "Ты ищешь ответ на вопрос ученика только среди материалов класса, которые тебе дали: "
    "расписание уроков, домашние задания, контрольные и события. "
    "Отвечай коротко и ссылайся на конкретную запись. "
    "Если в материалах ответа нет — так и скажи, ничего не придумывай. " + PLAIN_TEXT_RULE
)


@dataclass(frozen=True, slots=True)
class QuizQuestion:
    question: str
    options: list[str]
    correct_index: int
    explanation: str

    @property
    def correct_option(self) -> str:
        return self.options[self.correct_index]


@dataclass(frozen=True, slots=True)
class Quiz:
    topic: str
    questions: list[QuizQuestion]

    def __len__(self) -> int:
        return len(self.questions)


@dataclass(frozen=True, slots=True)
class HomeworkReview:
    score: int
    correct: list[str]
    mistakes: list[str]
    advice: str


class AssistantError(RuntimeError):
    pass


class AssistantDisabled(AssistantError):
    pass


class BadModelAnswer(AssistantError):
    pass


def extract_json(text: str) -> dict[str, Any]:
    """Достаёт JSON-объект из ответа модели, даже если он обёрнут в ```-блок."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", cleaned, flags=re.S)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise BadModelAnswer("модель вернула не JSON")
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise BadModelAnswer("не удалось разобрать JSON от модели") from exc
    if not isinstance(data, dict):
        raise BadModelAnswer("ожидался JSON-объект")
    return data


def _clean_strings(values: Any, *, limit: int) -> list[str]:
    if not isinstance(values, list):
        return []
    result = []
    for value in values:
        if isinstance(value, str) and value.strip():
            result.append(value.strip()[:limit])
    return result


def build_quiz(topic: str, payload: dict[str, Any]) -> Quiz:
    """Собирает тест из ответа модели, выкидывая явно поломанные вопросы."""
    raw_questions = payload.get("questions")
    if not isinstance(raw_questions, list):
        raise BadModelAnswer("в ответе нет списка вопросов")

    questions: list[QuizQuestion] = []
    for item in raw_questions:
        if not isinstance(item, dict):
            continue
        text = item.get("question")
        options = _clean_strings(item.get("options"), limit=120)[:MAX_OPTIONS]
        index = item.get("correct_index")
        if not isinstance(text, str) or not text.strip() or len(options) < 2:
            continue
        if not isinstance(index, int) or not 0 <= index < len(options):
            continue
        explanation = item.get("explanation")
        questions.append(
            QuizQuestion(
                question=text.strip()[:400],
                options=options,
                correct_index=index,
                explanation=explanation.strip()[:500] if isinstance(explanation, str) else "",
            )
        )
        if len(questions) == MAX_QUIZ_QUESTIONS:
            break

    if not questions:
        raise BadModelAnswer("модель не прислала ни одного корректного вопроса")
    return Quiz(topic=topic, questions=questions)


def build_review(payload: dict[str, Any]) -> HomeworkReview:
    score = payload.get("score")
    if not isinstance(score, int):
        try:
            score = int(str(score).strip())
        except (TypeError, ValueError):
            score = 3
    advice = payload.get("advice")
    return HomeworkReview(
        score=max(1, min(score, 5)),
        correct=_clean_strings(payload.get("correct"), limit=300)[:5],
        mistakes=_clean_strings(payload.get("mistakes"), limit=300)[:5],
        advice=advice.strip()[:400] if isinstance(advice, str) else "",
    )


def describe_error(exc: Exception) -> str:
    if isinstance(exc, AssistantDisabled):
        return (
            "ИИ-функции не настроены: администратору бота нужно добавить GIGACHAT_AUTH_KEY "
            "в настройки."
        )
    if isinstance(exc, BadModelAnswer):
        return "Модель ответила в неожиданном формате. Попробуй ещё раз или переформулируй."
    if isinstance(exc, GigaChatError):
        if exc.is_auth_error:
            return "Ключ GigaChat не подошёл — обратитесь к администратору бота."
        if exc.status == 429:
            return "Слишком много запросов к GigaChat, попробуй через минуту."
        if exc.status == 422:
            return "Запрос получился слишком большим. Попробуй сократить текст."
        return "GigaChat вернул ошибку, попробуй ещё раз позже."
    if isinstance(exc, GigaChatNetworkError):
        return "Не получилось связаться с GigaChat. Попробуй ещё раз через минуту."
    return "Что-то пошло не так при обращении к ИИ. Попробуй ещё раз."


class Assistant:
    """Прикладной слой поверх GigaChat: вопросы, тесты, проверка работ, поиск."""

    def __init__(self, client: GigaChatClient | None) -> None:
        self._client = client

    @property
    def enabled(self) -> bool:
        return self._client is not None

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()

    def _require(self) -> GigaChatClient:
        if self._client is None:
            raise AssistantDisabled("GigaChat не настроен")
        return self._client

    async def ask(self, question: str, *, context: str = "") -> str:
        client = self._require()
        content = question if not context else f"{question}\n\nЧто известно об ученике:\n{context}"
        answer = await client.chat(
            [
                {"role": "system", "content": ASK_SYSTEM},
                {"role": "user", "content": content},
            ],
            max_tokens=1200,
            temperature=0.3,
        )
        return answer or "Не получилось сформулировать ответ, попробуй спросить иначе."

    async def make_quiz(self, topic: str, count: int = 5) -> Quiz:
        client = self._require()
        count = max(MIN_QUIZ_QUESTIONS, min(count, MAX_QUIZ_QUESTIONS))
        answer = await client.chat(
            [
                {"role": "system", "content": QUIZ_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"Составь тест из {count} вопросов по теме «{topic}» из школьной программы. "
                        "У каждого вопроса ровно четыре варианта ответа и одно короткое пояснение."
                    ),
                },
            ],
            max_tokens=2500,
            temperature=0.6,
            response_format={"type": "json_schema", "schema": QUIZ_SCHEMA, "strict": True},
        )
        return build_quiz(topic, extract_json(answer))

    async def review(self, subject: str, task: str, answer: str) -> HomeworkReview:
        client = self._require()
        response = await client.chat(
            [
                {"role": "system", "content": REVIEW_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"Предмет: {subject}\nЗадание: {task}\n\nРабота ученика:\n{answer}\n\n"
                        "Проверь работу и дай обратную связь."
                    ),
                },
            ],
            max_tokens=1500,
            temperature=0.2,
            response_format={"type": "json_schema", "schema": REVIEW_SCHEMA, "strict": True},
        )
        return build_review(extract_json(response))

    async def search(self, query: str, materials: str) -> str:
        client = self._require()
        if not materials.strip():
            return "Пока нечего искать: в этом чате ещё нет расписания, домашки и событий."
        answer = await client.chat(
            [
                {"role": "system", "content": SEARCH_SYSTEM},
                {"role": "user", "content": f"Материалы класса:\n{materials}\n\nВопрос: {query}"},
            ],
            max_tokens=800,
            temperature=0.1,
        )
        return answer or "Не нашла ответа в материалах класса."
