from __future__ import annotations

from .. import keyboards as kb
from ..router import Router


async def render(ctx) -> None:
    settings = await ctx.storage.get_chat_settings(ctx.chat_id)
    text = (
        "Настройки\n\n"
        f"Утренний дайджест: {settings.morning_digest_at or ctx.config.morning_digest_at}\n"
        f"Вечерний дайджест: {settings.evening_digest_at or ctx.config.evening_digest_at}\n"
        f"Часовой пояс: UTC{settings.tz_offset:+d} (поменять — /timezone +3)\n"
        f"Дайджест: {'включён' if settings.digest_enabled else 'выключен'}"
    )
    await ctx.show(text, keyboard=kb.settings_menu(settings.digest_enabled))


def register(router: Router) -> None:
    @router.callback("set")
    async def set_callback(ctx, args: list[str]) -> None:
        if not args or args[0] != "digest":
            return
        current = await ctx.storage.get_chat_settings(ctx.chat_id)
        new_value = not current.digest_enabled
        await ctx.storage.update_chat_settings(ctx.chat_id, digest_enabled=int(new_value))
        await ctx.toast("Дайджест включён" if new_value else "Дайджест выключен")
        await render(ctx)

    @router.command("/timezone", "/tz")
    async def timezone_cmd(ctx, args: str) -> None:
        args = args.strip()
        if not args:
            settings = await ctx.storage.get_chat_settings(ctx.chat_id)
            await ctx.reply(f"Текущий часовой пояс: UTC{settings.tz_offset:+d}. Чтобы изменить: /timezone +3")
            return
        try:
            offset = int(args.replace("UTC", "").replace("utc", "").strip())
        except ValueError:
            await ctx.reply("Не поняла. Пример: /timezone +3")
            return
        if not (-12 <= offset <= 14):
            await ctx.reply("Смещение должно быть от -12 до +14.")
            return
        await ctx.storage.update_chat_settings(ctx.chat_id, tz_offset=offset)
        await ctx.reply(f"Готово, часовой пояс UTC{offset:+d}.")
