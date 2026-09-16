from __future__ import annotations

from datetime import date

from .. import keyboards as kb
from ...domain import dates as dt
from ...domain import homework as homework_domain
from ..router import Router


async def render_list(ctx) -> None:
    items = await ctx.storage.list_homework(ctx.chat_id, ctx.user_id or 0)
    visible = [hw for hw in items if hw.due_date >= ctx.today or not hw.done]
    text = homework_domain.format_list(visible, today_date=ctx.today)
    ordered = sorted(visible, key=lambda hw: (hw.due_date, hw.subject.lower()))[:25]
    keyboard = kb.homework_list_keyboard([(hw.id, hw.done) for hw in ordered])
    await ctx.show(text, keyboard=keyboard)


def register(router: Router) -> None:
    @router.command("/homework", "/hw")
    async def homework_cmd(ctx, args: str) -> None:
        await render_list(ctx)

    @router.callback("hw")
    async def hw_callback(ctx, args: list[str]) -> None:
        if not args:
            return
        action = args[0]

        if action == "list":
            await render_list(ctx)
            return

        if action == "add":
            await ctx.set_pending("add_homework", {"step": "subject"})
            await ctx.show("Какой предмет?", keyboard=kb.cancel_only())
            return

        if action == "done" and len(args) > 1 and args[1].isdigit() and ctx.user_id is not None:
            done = await ctx.storage.toggle_homework_done(int(args[1]), ctx.user_id)
            await ctx.toast("Отмечено выполненным" if done else "Возвращено в список")
            await render_list(ctx)
            return

        if action == "del" and len(args) > 1 and args[1].isdigit():
            removed = await ctx.storage.delete_homework(ctx.chat_id, int(args[1]))
            await ctx.toast("Удалено" if removed else "Уже удалено")
            await render_list(ctx)

    @router.flow("add_homework")
    async def add_homework_flow(ctx, text: str, data: dict) -> None:
        step = data.get("step")

        if step == "subject":
            subject = text.strip()
            if not subject:
                await ctx.reply("Название предмета не должно быть пустым.", keyboard=kb.cancel_only())
                return
            data["subject"] = subject[:100]
            data["step"] = "due_date"
            await ctx.set_pending("add_homework", data)
            await ctx.reply("На какое число? Например «завтра», «пятница» или «17.09».", keyboard=kb.cancel_only())
            return

        if step == "due_date":
            due = dt.parse_date(text, today_date=ctx.today)
            if due is None:
                await ctx.reply("Не поняла дату. Попробуй «завтра», «пятница» или «17.09».", keyboard=kb.cancel_only())
                return
            data["due_date"] = due.isoformat()
            data["step"] = "text"
            await ctx.set_pending("add_homework", data)
            await ctx.reply("Что задали?", keyboard=kb.cancel_only())
            return

        if step == "text":
            body = text.strip()
            if not body:
                await ctx.reply("Текст задания не должен быть пустым.", keyboard=kb.cancel_only())
                return
            due = date.fromisoformat(data["due_date"])
            name = ctx.user.name if ctx.user else ""
            await ctx.storage.add_homework(ctx.chat_id, data["subject"], due, body[:1000], ctx.user_id or 0, name)
            await ctx.clear_pending()
            await ctx.reply(f"Записала: {data['subject']} на {dt.format_relative_date(due, today_date=ctx.today)}.")
            await render_list(ctx)
