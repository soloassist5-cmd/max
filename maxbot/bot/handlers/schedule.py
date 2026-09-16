from __future__ import annotations

from datetime import timedelta

from .. import keyboards as kb
from ...domain import bells as bells_domain
from ...domain import dates as dt
from ...domain import events as events_domain
from ...domain import schedule as schedule_domain
from ...domain.dates import WEEKDAYS_FULL
from ..router import Router

WEEKDAY_WORDS = "\n".join(f"{i + 1} — {WEEKDAYS_FULL[i]}" for i in range(7))


async def _bells(ctx) -> list[bells_domain.Bell]:
    bells = await ctx.storage.get_bells(ctx.chat_id)
    return bells or list(bells_domain.DEFAULT_BELLS)


async def render_schedule_menu(ctx) -> None:
    await ctx.show("Расписание — выбери день:", keyboard=kb.schedule_menu(ctx.today.weekday()))


async def render_day(ctx, weekday: int) -> None:
    lessons = schedule_domain.by_weekday(await ctx.storage.list_lessons(ctx.chat_id), weekday)
    bells = await _bells(ctx)
    title = WEEKDAYS_FULL[weekday].capitalize()
    if weekday == ctx.today.weekday():
        title += " (сегодня)"
    text = f"{title}\n\n{schedule_domain.format_day(lessons, bells)}"
    await ctx.show(text, keyboard=kb.day_view(weekday, [lesson.id for lesson in lessons]))


async def render_week(ctx) -> None:
    lessons = await ctx.storage.list_lessons(ctx.chat_id)
    bells = await _bells(ctx)
    grouped = schedule_domain.group_by_weekday(lessons)
    await ctx.show(schedule_domain.format_week(grouped, bells), keyboard=kb.back_to_menu())


async def render_bells(ctx) -> None:
    bells = await _bells(ctx)
    state = bells_domain.current_state(bells, dt.now(ctx.tz_offset).time())
    lines = [bells_domain.format_bells(bells), ""]
    if state.phase == bells_domain.Phase.LESSON and state.current:
        lines.append(f"Сейчас урок №{state.current.number}, до конца {dt.minutes_phrase(state.minutes_left)}.")
    elif state.phase == bells_domain.Phase.BREAK and state.upcoming:
        lines.append(
            f"Сейчас перемена, урок №{state.upcoming.number} начнётся через {dt.minutes_phrase(state.minutes_left)}."
        )
    elif state.phase == bells_domain.Phase.BEFORE and state.upcoming:
        lines.append(f"Уроки ещё не начались, первый — через {dt.minutes_phrase(state.minutes_left)}.")
    else:
        lines.append("Уроки на сегодня закончились.")
    await ctx.show("\n".join(lines), keyboard=kb.bells_menu())


async def _render_day_digest(ctx, target_date) -> None:
    lessons = schedule_domain.by_weekday(await ctx.storage.list_lessons(ctx.chat_id), target_date.weekday())
    bells = await _bells(ctx)
    homework = await ctx.storage.list_homework_by_date(ctx.chat_id, target_date)
    events = [
        e for e in await ctx.storage.list_events(ctx.chat_id, from_date=target_date) if e.event_date == target_date
    ]

    lines = [dt.format_date(target_date).capitalize(), "", schedule_domain.format_day(lessons, bells)]
    if homework:
        lines += ["", "Сдать:"] + [f"• {item.subject} — {item.text}" for item in homework]
    if events:
        lines += ["", "События:"] + [
            f"• {events_domain.format_event(e, today_date=ctx.today)}" for e in events
        ]
    await ctx.show("\n".join(lines))


def _parse_weekday_input(text: str) -> int | None:
    cleaned = text.strip()
    if cleaned.isdigit():
        value = int(cleaned)
        return value - 1 if 1 <= value <= 7 else None
    return dt.parse_weekday(cleaned)


def register(router: Router) -> None:
    @router.command("/today")
    async def today(ctx, args: str) -> None:
        await _render_day_digest(ctx, ctx.today)

    @router.command("/tomorrow")
    async def tomorrow(ctx, args: str) -> None:
        await _render_day_digest(ctx, ctx.today + timedelta(days=1))

    @router.command("/week")
    async def week(ctx, args: str) -> None:
        await render_week(ctx)

    @router.command("/bells")
    async def bells_cmd(ctx, args: str) -> None:
        await render_bells(ctx)

    @router.callback("day")
    async def day_callback(ctx, args: list[str]) -> None:
        if args and args[0].isdigit() and 0 <= int(args[0]) <= 6:
            await render_day(ctx, int(args[0]))

    @router.callback("sched")
    async def sched_callback(ctx, args: list[str]) -> None:
        if not args:
            return
        action = args[0]

        if action == "week":
            await render_week(ctx)
            return

        if action == "add":
            await ctx.set_pending("add_lesson", {"step": "weekday"})
            await ctx.show(
                f"На какой день недели урок?\n\n{WEEKDAY_WORDS}\n\nНапиши день словом или числом.",
                keyboard=kb.cancel_only(),
            )
            return

        if action == "addto" and len(args) > 1 and args[1].isdigit():
            weekday = int(args[1])
            await ctx.set_pending("add_lesson", {"step": "slot", "weekday": weekday})
            await ctx.show("Каким по счёту уроком? Например 3.", keyboard=kb.cancel_only())
            return

        if action == "del" and len(args) > 1 and args[1].isdigit():
            lesson = await ctx.storage.get_lesson(ctx.chat_id, int(args[1]))
            if lesson is None:
                await ctx.toast("Урок уже удалён")
                return
            await ctx.storage.remove_lesson(ctx.chat_id, lesson.id)
            await ctx.toast("Урок удалён")
            await render_day(ctx, lesson.weekday)

    @router.callback("bells")
    async def bells_callback(ctx, args: list[str]) -> None:
        if not args:
            return
        if args[0] == "set":
            await ctx.set_pending("set_bells", {})
            example = "1. 8:30-9:15\n2. 9:25-10:10"
            await ctx.show(
                f"Пришли расписание звонков — по строке на урок, формат «номер. начало-конец».\nНапример:\n{example}",
                keyboard=kb.cancel_only(),
            )
        elif args[0] == "reset":
            await ctx.storage.set_bells(ctx.chat_id, [])
            await ctx.toast("Сброшено на стандартное")
            await render_bells(ctx)

    @router.flow("add_lesson")
    async def add_lesson_flow(ctx, text: str, data: dict) -> None:
        step = data.get("step")

        if step == "weekday":
            weekday = _parse_weekday_input(text)
            if weekday is None:
                await ctx.reply("Не поняла день недели. Напиши, например, «вторник» или «2».", keyboard=kb.cancel_only())
                return
            data["weekday"] = weekday
            data["step"] = "slot"
            await ctx.set_pending("add_lesson", data)
            await ctx.reply("Каким по счёту уроком? Например 3.", keyboard=kb.cancel_only())
            return

        if step == "slot":
            if not text.isdigit() or not (1 <= int(text) <= 12):
                await ctx.reply("Нужно число от 1 до 12.", keyboard=kb.cancel_only())
                return
            data["slot"] = int(text)
            data["step"] = "subject"
            await ctx.set_pending("add_lesson", data)
            await ctx.reply("Какой предмет?", keyboard=kb.cancel_only())
            return

        if step == "subject":
            subject = text.strip()
            if not subject:
                await ctx.reply("Название предмета не должно быть пустым.", keyboard=kb.cancel_only())
                return
            data["subject"] = subject[:100]
            data["step"] = "room"
            await ctx.set_pending("add_lesson", data)
            await ctx.reply("Кабинет? Если не нужно — отправь «-».", keyboard=kb.cancel_only())
            return

        if step == "room":
            room = None if text.strip() == "-" else text.strip()[:50]
            await ctx.storage.upsert_lesson(ctx.chat_id, data["weekday"], data["slot"], data["subject"], room=room)
            await ctx.clear_pending()
            await ctx.reply(f"Готово: {WEEKDAYS_FULL[data['weekday']]}, урок {data['slot']} — {data['subject']}.")
            await render_day(ctx, data["weekday"])

    @router.flow("set_bells")
    async def set_bells_flow(ctx, text: str, data: dict) -> None:
        parsed = bells_domain.parse_bells(text)
        if not parsed:
            await ctx.reply(
                "Не смогла разобрать расписание. Формат: «1. 8:30-9:15», по строке на урок.",
                keyboard=kb.cancel_only(),
            )
            return
        await ctx.storage.set_bells(ctx.chat_id, parsed)
        await ctx.clear_pending()
        await ctx.reply(f"Сохранила расписание звонков:\n\n{bells_domain.format_bells(parsed)}")
