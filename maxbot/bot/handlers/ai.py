from __future__ import annotations

from typing import Any

from .. import keyboards as kb
from ...ai import describe_error
from ...ai.assistant import Quiz, QuizQuestion
from ...domain import events as events_domain
from ...domain import homework as homework_domain
from ...domain import schedule as schedule_domain
from ..router import Router

THINKING = "Думаю…"
MATERIALS_LIMIT = 6000

QUIZ_STATE = "quiz_active"


async def _guard(ctx) -> bool:
    if ctx.ai.enabled:
        return True
    await ctx.show(
        "ИИ-функции пока не подключены. Администратору бота нужно добавить GIGACHAT_AUTH_KEY "
        "в настройки — ключ выдаётся в личном кабинете GigaChat API.",
        keyboard=kb.back_to_menu(),
    )
    return False


async def _collect_materials(ctx) -> str:
    """Всё, что бот знает про класс, одним текстом — контекст для поиска."""
    lessons = await ctx.storage.list_lessons(ctx.chat_id)
    bells = await ctx.storage.get_bells(ctx.chat_id)
    homework = await ctx.storage.list_homework(ctx.chat_id, ctx.user_id or 0)
    events = await ctx.storage.list_events(ctx.chat_id, from_date=ctx.today)

    blocks = [f"Сегодня: {ctx.today.isoformat()}"]
    if lessons:
        week = schedule_domain.format_week(schedule_domain.group_by_weekday(lessons), bells)
        blocks.append(f"Расписание уроков:\n{week}")
    if homework:
        blocks.append(f"Домашние задания:\n{homework_domain.format_list(homework, today_date=ctx.today)}")
    if events:
        blocks.append(f"Контрольные и события:\n{events_domain.format_list(events, today_date=ctx.today)}")

    return "\n\n".join(blocks)[:MATERIALS_LIMIT] if len(blocks) > 1 else ""


def _format_review(review) -> str:
    lines = [f"Оценка за работу: {review.score} из 5"]
    if review.correct:
        lines += ["", "Получилось:"] + [f"+ {item}" for item in review.correct]
    if review.mistakes:
        lines += ["", "Стоит исправить:"] + [f"- {item}" for item in review.mistakes]
    if review.advice:
        lines += ["", f"Совет: {review.advice}"]
    return "\n".join(lines)


def _quiz_to_data(quiz: Quiz) -> dict[str, Any]:
    return {
        "topic": quiz.topic,
        "index": 0,
        "score": 0,
        "questions": [
            {
                "question": item.question,
                "options": item.options,
                "correct_index": item.correct_index,
                "explanation": item.explanation,
            }
            for item in quiz.questions
        ],
    }


def _question_at(data: dict[str, Any], index: int) -> QuizQuestion | None:
    questions = data.get("questions") or []
    if not 0 <= index < len(questions):
        return None
    item = questions[index]
    return QuizQuestion(
        question=item["question"],
        options=list(item["options"]),
        correct_index=item["correct_index"],
        explanation=item.get("explanation", ""),
    )


async def _show_question(ctx, data: dict[str, Any]) -> None:
    index = data["index"]
    question = _question_at(data, index)
    if question is None:
        await _show_result(ctx, data)
        return
    total = len(data["questions"])
    text = f"Тест: {data['topic']}\nВопрос {index + 1} из {total}\n\n{question.question}"
    await ctx.show(text, keyboard=kb.quiz_options(question.options))


async def _show_result(ctx, data: dict[str, Any]) -> None:
    await ctx.clear_pending()
    score, total = data["score"], len(data["questions"])
    if total and score == total:
        verdict = "идеально!"
    elif total and score * 2 >= total:
        verdict = "неплохо, но есть что повторить."
    else:
        verdict = "тему стоит разобрать ещё раз."
    await ctx.show(
        f"Тест по теме «{data['topic']}» закончен.\nРезультат: {score} из {total} — {verdict}",
        keyboard=kb.ai_again("quiz"),
    )


async def _run_quiz(ctx, topic: str) -> None:
    await ctx.show(f"Составляю тест по теме «{topic}»…")
    try:
        quiz = await ctx.ai.make_quiz(topic)
    except Exception as exc:
        await ctx.reply(describe_error(exc), keyboard=kb.ai_again("quiz"))
        return
    data = _quiz_to_data(quiz)
    await ctx.set_pending(QUIZ_STATE, data)
    await _show_question(ctx, data)


async def _run_ask(ctx, question: str) -> None:
    await ctx.show(THINKING)
    try:
        answer = await ctx.ai.ask(question)
    except Exception as exc:
        await ctx.reply(describe_error(exc), keyboard=kb.ai_again("ask"))
        return
    await ctx.reply(answer, keyboard=kb.ai_again("ask"))


async def _run_find(ctx, query: str) -> None:
    await ctx.show("Ищу в материалах класса…")
    materials = await _collect_materials(ctx)
    try:
        answer = await ctx.ai.search(query, materials)
    except Exception as exc:
        await ctx.reply(describe_error(exc), keyboard=kb.ai_again("find"))
        return
    await ctx.reply(answer, keyboard=kb.ai_again("find"))


def register(router: Router) -> None:
    @router.command("/ask")
    async def ask_cmd(ctx, args: str) -> None:
        if not await _guard(ctx):
            return
        if args.strip():
            await _run_ask(ctx, args.strip())
            return
        await ctx.set_pending("ask_question", {})
        await ctx.reply("О чём спросить? Напиши вопрос по любому предмету.", keyboard=kb.cancel_only())

    @router.command("/quiz")
    async def quiz_cmd(ctx, args: str) -> None:
        if not await _guard(ctx):
            return
        if args.strip():
            await _run_quiz(ctx, args.strip()[:120])
            return
        await ctx.set_pending("quiz_topic", {})
        await ctx.reply(
            "По какой теме сделать тест? Например «Фотосинтез» или «Дроби».",
            keyboard=kb.cancel_only(),
        )

    @router.command("/check")
    async def check_cmd(ctx, args: str) -> None:
        if not await _guard(ctx):
            return
        await ctx.set_pending("check_work", {"step": "subject"})
        await ctx.reply("По какому предмету работа?", keyboard=kb.cancel_only())

    @router.command("/find")
    async def find_cmd(ctx, args: str) -> None:
        if not await _guard(ctx):
            return
        if args.strip():
            await _run_find(ctx, args.strip())
            return
        await ctx.set_pending("find_query", {})
        await ctx.reply(
            "Что найти? Например «когда контрольная по химии» или «что задали по алгебре».",
            keyboard=kb.cancel_only(),
        )

    @router.callback("ai")
    async def ai_callback(ctx, args: list[str]) -> None:
        if not args or not await _guard(ctx):
            return
        action = args[0]

        if action == "ask":
            await ctx.set_pending("ask_question", {})
            await ctx.show("О чём спросить? Напиши вопрос по любому предмету.", keyboard=kb.cancel_only())
        elif action == "quiz":
            await ctx.set_pending("quiz_topic", {})
            await ctx.show(
                "По какой теме сделать тест? Например «Фотосинтез» или «Дроби».",
                keyboard=kb.cancel_only(),
            )
        elif action == "check":
            await ctx.set_pending("check_work", {"step": "subject"})
            await ctx.show("По какому предмету работа?", keyboard=kb.cancel_only())
        elif action == "find":
            await ctx.set_pending("find_query", {})
            await ctx.show(
                "Что найти? Например «когда контрольная по химии» или «что задали по алгебре».",
                keyboard=kb.cancel_only(),
            )

    @router.callback("quiz")
    async def quiz_callback(ctx, args: list[str]) -> None:
        if not args or ctx.user_id is None:
            return
        pending = await ctx.storage.get_pending(ctx.chat_id, ctx.user_id)
        if not pending or pending[0] != QUIZ_STATE:
            await ctx.toast("Тест уже завершён")
            return
        data = pending[1]
        action = args[0]

        if action == "stop":
            await _show_result(ctx, data)
            return

        if action == "next":
            data["index"] += 1
            await ctx.set_pending(QUIZ_STATE, data)
            await _show_question(ctx, data)
            return

        if action == "answer" and len(args) > 1 and args[1].isdigit():
            question = _question_at(data, data["index"])
            if question is None:
                await _show_result(ctx, data)
                return
            chosen = int(args[1])
            correct = chosen == question.correct_index
            if correct:
                data["score"] += 1
            await ctx.set_pending(QUIZ_STATE, data)

            total = len(data["questions"])
            head = "Верно!" if correct else f"Неверно. Правильный ответ: {question.correct_option}"
            lines = [head]
            if question.explanation:
                lines += ["", question.explanation]
            lines += ["", f"Счёт: {data['score']} из {data['index'] + 1}"]
            await ctx.show("\n".join(lines), keyboard=kb.quiz_next(data["index"] + 1 >= total))

    @router.flow("ask_question")
    async def ask_flow(ctx, text: str, data: dict) -> None:
        await ctx.clear_pending()
        await _run_ask(ctx, text)

    @router.flow("quiz_topic")
    async def quiz_topic_flow(ctx, text: str, data: dict) -> None:
        await ctx.clear_pending()
        await _run_quiz(ctx, text[:120])

    @router.flow("find_query")
    async def find_flow(ctx, text: str, data: dict) -> None:
        await ctx.clear_pending()
        await _run_find(ctx, text)

    @router.flow(QUIZ_STATE)
    async def quiz_guard_flow(ctx, text: str, data: dict) -> None:
        await ctx.reply("Сейчас идёт тест — выбери вариант кнопкой под вопросом или нажми «Закончить».")

    @router.flow("check_work")
    async def check_flow(ctx, text: str, data: dict) -> None:
        step = data.get("step")

        if step == "subject":
            data["subject"] = text.strip()[:100]
            data["step"] = "task"
            await ctx.set_pending("check_work", data)
            await ctx.reply("Что было задано? Опиши задание в двух словах.", keyboard=kb.cancel_only())
            return

        if step == "task":
            data["task"] = text.strip()[:500]
            data["step"] = "answer"
            await ctx.set_pending("check_work", data)
            await ctx.reply("Теперь пришли свою работу или решение целиком.", keyboard=kb.cancel_only())
            return

        if step == "answer":
            await ctx.clear_pending()
            await ctx.reply("Проверяю…")
            try:
                review = await ctx.ai.review(data["subject"], data["task"], text[:4000])
            except Exception as exc:
                await ctx.reply(describe_error(exc), keyboard=kb.ai_again("check"))
                return
            await ctx.reply(_format_review(review), keyboard=kb.ai_again("check"))
