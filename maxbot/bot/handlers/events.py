from __future__ import annotations

from datetime import date

from .. import keyboards as kb
from ...domain import dates as dt
from ...domain import events as events_domain
from ..router import Router


async def render_list(ctx) -> None:
    items = await ctx.storage.list_events(ctx.chat_id, from_date=ctx.today)
    text = events_domain.format_list(items, today_date=ctx.today)
    ordered = events_domain.upcoming(items, today_date=ctx.today)[:25]
    keyboard = kb.events_list_keyboard([e.id for e in ordered])
    await ctx.show(text, keyboard=keyboard)


def register(router: Router) -> None:
    @router.command("/events", "/ev")
    async def events_cmd(ctx, args: str) -> None:
        await render_list(ctx)

    @router.callback("ev")
    async def ev_callback(ctx, args: list[str]) -> None:
        if not args:
            return
        action = args[0]

        if action == "list":
            await render_list(ctx)
            return

        if action == "add":
            await ctx.set_pending("add_event", {"step": "kind"})
            await ctx.show(
                "Что за событие? Например «Контрольная», «Экзамен» или «Сдача проекта».",
                keyboard=kb.cancel_only(),
            )
            return

        if action == "del" and len(args) > 1 and args[1].isdigit():
            removed = await ctx.storage.delete_event(ctx.chat_id, int(args[1]))
            await ctx.toast("Удалено" if removed else "Уже удалено")
            await render_list(ctx)

    @router.flow("add_event")
    async def add_event_flow(ctx, text: str, data: dict) -> None:
        step = data.get("step")

        if step == "kind":
            kind = text.strip()
            if not kind:
                await ctx.reply("Не должно быть пустым.", keyboard=kb.cancel_only())
                return
            data["kind"] = kind[:60]
            data["step"] = "title"
            await ctx.set_pending("add_event", data)
            await ctx.reply("По какому предмету или о чём именно?", keyboard=kb.cancel_only())
            return

        if step == "title":
            title = text.strip()
            if not title:
                await ctx.reply("Не должно быть пустым.", keyboard=kb.cancel_only())
                return
            data["title"] = title[:150]
            data["step"] = "date"
            await ctx.set_pending("add_event", data)
            await ctx.reply("На какое число? Например «пятница» или «24.09».", keyboard=kb.cancel_only())
            return

        if step == "date":
            event_date = dt.parse_date(text, today_date=ctx.today)
            if event_date is None:
                await ctx.reply("Не поняла дату. Попробуй «пятница» или «24.09».", keyboard=kb.cancel_only())
                return
            data["date"] = event_date.isoformat()
            data["step"] = "time"
            await ctx.set_pending("add_event", data)
            await ctx.reply("Во сколько? Формат «10:00». Если неважно — отправь «-».", keyboard=kb.cancel_only())
            return

        if step == "time":
            event_time = None
            if text.strip() != "-":
                event_time = dt.parse_time(text)
                if event_time is None:
                    await ctx.reply("Не поняла время. Формат «10:00» или «-», если неважно.", keyboard=kb.cancel_only())
                    return
            event_date = date.fromisoformat(data["date"])
            name = ctx.user.name if ctx.user else ""
            await ctx.storage.add_event(
                ctx.chat_id, data["title"], data["kind"], event_date, event_time, ctx.user_id or 0, name,
            )
            await ctx.clear_pending()
            await ctx.reply(f"Записала: {data['kind']} — {data['title']}.")
            await render_list(ctx)
