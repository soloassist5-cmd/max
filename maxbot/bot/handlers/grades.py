from __future__ import annotations

from .. import keyboards as kb
from ...domain import grades as grades_domain
from ..router import Router


async def render_list(ctx) -> None:
    items = await ctx.storage.list_grades(ctx.chat_id, ctx.user_id or 0)
    text = grades_domain.format_grades(items)
    ordered = sorted(items, key=lambda g: g.created_at)[-25:]
    keyboard = kb.grades_list_keyboard([g.id for g in ordered])
    await ctx.show(text, keyboard=keyboard)


def register(router: Router) -> None:
    @router.command("/grades", "/gr")
    async def grades_cmd(ctx, args: str) -> None:
        await render_list(ctx)

    @router.callback("gr")
    async def gr_callback(ctx, args: list[str]) -> None:
        if not args:
            return
        action = args[0]

        if action == "list":
            await render_list(ctx)
            return

        if action == "add":
            await ctx.set_pending("add_grade", {"step": "subject"})
            await ctx.show("Какой предмет?", keyboard=kb.cancel_only())
            return

        if action == "del" and len(args) > 1 and args[1].isdigit() and ctx.user_id is not None:
            removed = await ctx.storage.delete_grade(ctx.chat_id, ctx.user_id, int(args[1]))
            await ctx.toast("Удалено" if removed else "Уже удалено")
            await render_list(ctx)

    @router.flow("add_grade")
    async def add_grade_flow(ctx, text: str, data: dict) -> None:
        step = data.get("step")

        if step == "subject":
            subject = text.strip()
            if not subject:
                await ctx.reply("Название предмета не должно быть пустым.", keyboard=kb.cancel_only())
                return
            data["subject"] = subject[:100]
            data["step"] = "value"
            await ctx.set_pending("add_grade", data)
            await ctx.reply("Какая оценка? Число от 1 до 5.", keyboard=kb.cancel_only())
            return

        if step == "value":
            if not text.strip().isdigit() or not (1 <= int(text.strip()) <= 5):
                await ctx.reply("Нужно число от 1 до 5.", keyboard=kb.cancel_only())
                return
            data["value"] = int(text.strip())
            data["step"] = "note"
            await ctx.set_pending("add_grade", data)
            await ctx.reply("За что оценка? Например «контрольная». Если не важно — отправь «-».", keyboard=kb.cancel_only())
            return

        if step == "note":
            if ctx.user_id is None:
                await ctx.clear_pending()
                return
            note = "" if text.strip() == "-" else text.strip()[:200]
            await ctx.storage.add_grade(ctx.chat_id, ctx.user_id, data["subject"], data["value"], note)
            await ctx.clear_pending()
            suffix = f" ({note})" if note else ""
            await ctx.reply(f"Записала: {data['subject']} — {data['value']}{suffix}.")
            await render_list(ctx)
