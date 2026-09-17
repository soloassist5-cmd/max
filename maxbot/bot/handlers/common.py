from __future__ import annotations

from .. import keyboards as kb
from ..router import Router
from . import schedule, settings

HELP_TEXT = (
    "Вот что я умею:\n\n"
    "/today — расписание и дела на сегодня\n"
    "/tomorrow — то же самое на завтра\n"
    "/week — расписание на неделю\n"
    "/bells — звонки и сколько осталось до конца урока\n"
    "/homework — домашние задания\n"
    "/grades — оценки\n"
    "/events — контрольные, экзамены, дедлайны\n"
    "/timezone — часовой пояс для дайджестов\n"
    "/menu — открыть меню с кнопками\n\n"
    "ИИ-помощник (работает на GigaChat):\n"
    "/ask — объяснить тему или разобрать задачу\n"
    "/quiz — тест с вариантами ответа по любой теме\n"
    "/check — проверить свою работу и получить разбор\n"
    "/find — найти ответ в расписании, домашке и контрольных\n\n"
    "Расписание, домашку и события в общем чате может редактировать любой участник — "
    "это общий список для всего класса. Оценки у каждого свои."
)

START_TEXT = (
    "Привет{name}! Я школьный бот-помощник 🎒\n\n"
    "Слежу за расписанием уроков и звонков, домашкой, оценками и контрольными, "
    "а по утрам и вечерам сама напоминаю, что нас ждёт.\n\n"
    "Ещё умею объяснять темы, делать тесты и проверять работы — это раздел «ИИ-помощник».\n\n"
    "Выбирай раздел кнопками ниже или набери /help."
)


def register(router: Router) -> None:
    @router.command("/start")
    async def start(ctx, args: str) -> None:
        name = f", {ctx.user.first_name}" if ctx.user else ""
        await ctx.reply(START_TEXT.format(name=name), keyboard=kb.main_menu())

    @router.command("/help")
    async def help_(ctx, args: str) -> None:
        await ctx.reply(HELP_TEXT)

    @router.command("/menu")
    async def menu(ctx, args: str) -> None:
        await ctx.show("Выбирай раздел:", keyboard=kb.main_menu())

    @router.callback("menu")
    async def menu_callback(ctx, args: list[str]) -> None:
        section = args[0] if args else "root"

        if section == "schedule":
            await schedule.render_schedule_menu(ctx)
        elif section == "bells":
            await schedule.render_bells(ctx)
        elif section == "homework":
            await ctx.show("Домашние задания:", keyboard=kb.homework_menu())
        elif section == "grades":
            await ctx.show("Оценки:", keyboard=kb.grades_menu())
        elif section == "events":
            await ctx.show("Контрольные и дедлайны:", keyboard=kb.events_menu())
        elif section == "ai":
            await ctx.show("ИИ-помощник — что нужно?", keyboard=kb.ai_menu())
        elif section == "settings":
            await settings.render(ctx)
        elif section == "help":
            await ctx.show(HELP_TEXT, keyboard=kb.back_to_menu())
        else:
            await ctx.show("Выбирай раздел:", keyboard=kb.main_menu())

    @router.callback("flow")
    async def flow_callback(ctx, args: list[str]) -> None:
        if args and args[0] == "cancel":
            await ctx.clear_pending()
            await ctx.show("Отменила. Выбирай раздел:", keyboard=kb.main_menu())
