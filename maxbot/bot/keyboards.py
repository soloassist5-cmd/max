from __future__ import annotations

from ..api import keyboard as btn
from ..domain.dates import WEEKDAYS_SHORT


def main_menu() -> dict:
    return btn.keyboard(
        [btn.callback("📅 Расписание", "menu:schedule"), btn.callback("🔔 Звонки", "menu:bells")],
        [btn.callback("📝 Домашка", "menu:homework"), btn.callback("🎯 Оценки", "menu:grades")],
        [btn.callback("⏰ Контрольные", "menu:events"), btn.callback("⚙️ Настройки", "menu:settings")],
        [btn.callback("❓ Помощь", "menu:help")],
    )


def back_to_menu() -> dict:
    return btn.keyboard([btn.callback("⬅️ Меню", "menu:root")])


def cancel_only() -> dict:
    return btn.keyboard([btn.callback("Отмена", "flow:cancel")])


def schedule_menu(today_weekday: int) -> dict:
    days = [
        btn.callback(f"• {WEEKDAYS_SHORT[i]} •" if i == today_weekday else WEEKDAYS_SHORT[i], f"day:{i}")
        for i in range(7)
    ]
    return btn.keyboard(
        days[:4],
        days[4:],
        [btn.callback("📋 Вся неделя", "sched:week")],
        [btn.callback("➕ Добавить урок", "sched:add"), btn.callback("🔔 Звонки", "menu:bells")],
        [btn.callback("⬅️ Меню", "menu:root")],
    )


def day_view(weekday: int, lesson_ids: list[int]) -> dict:
    rows = [[btn.callback(f"🗑 Урок {i + 1}", f"sched:del:{lesson_id}")] for i, lesson_id in enumerate(lesson_ids)]
    rows.append([btn.callback("➕ Добавить сюда", f"sched:addto:{weekday}")])
    rows.append([btn.callback("⬅️ Дни недели", "menu:schedule")])
    return btn.keyboard(*rows)


def bells_menu() -> dict:
    return btn.keyboard(
        [btn.callback("✏️ Задать своё расписание", "bells:set")],
        [btn.callback("↩️ Сбросить на стандартное", "bells:reset")],
        [btn.callback("⬅️ Меню", "menu:root")],
    )


def homework_menu() -> dict:
    return btn.keyboard(
        [btn.callback("📋 Показать всё", "hw:list"), btn.callback("➕ Добавить", "hw:add")],
        [btn.callback("⬅️ Меню", "menu:root")],
    )


def homework_list_keyboard(items: list[tuple[int, bool]]) -> dict:
    rows = []
    for homework_id, done in items:
        mark = "↩️ Вернуть" if done else "✅ Готово"
        rows.append([btn.callback(mark, f"hw:done:{homework_id}"), btn.callback("🗑", f"hw:del:{homework_id}")])
    rows.append([btn.callback("➕ Добавить", "hw:add"), btn.callback("⬅️ Меню", "menu:root")])
    return btn.keyboard(*rows)


def grades_menu() -> dict:
    return btn.keyboard(
        [btn.callback("📋 Показать", "gr:list"), btn.callback("➕ Добавить", "gr:add")],
        [btn.callback("⬅️ Меню", "menu:root")],
    )


def grades_list_keyboard(ids: list[int]) -> dict:
    rows = [[btn.callback(f"🗑 Удалить #{gid}", f"gr:del:{gid}")] for gid in ids]
    rows.append([btn.callback("➕ Добавить", "gr:add"), btn.callback("⬅️ Меню", "menu:root")])
    return btn.keyboard(*rows)


def events_menu() -> dict:
    return btn.keyboard(
        [btn.callback("📋 Показать", "ev:list"), btn.callback("➕ Добавить", "ev:add")],
        [btn.callback("⬅️ Меню", "menu:root")],
    )


def events_list_keyboard(ids: list[int]) -> dict:
    rows = [[btn.callback(f"🗑 Удалить #{eid}", f"ev:del:{eid}")] for eid in ids]
    rows.append([btn.callback("➕ Добавить", "ev:add"), btn.callback("⬅️ Меню", "menu:root")])
    return btn.keyboard(*rows)


def settings_menu(digest_enabled: bool) -> dict:
    toggle = btn.callback("🔕 Выключить дайджест" if digest_enabled else "🔔 Включить дайджест", "set:digest")
    return btn.keyboard([toggle], [btn.callback("⬅️ Меню", "menu:root")])
