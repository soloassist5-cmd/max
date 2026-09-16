from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .bells import Bell
from .dates import WEEKDAYS_FULL, format_time


@dataclass(frozen=True, slots=True)
class Lesson:
    id: int
    weekday: int
    slot: int
    subject: str
    room: str | None = None
    teacher: str | None = None


def by_weekday(lessons: Iterable[Lesson], weekday: int) -> list[Lesson]:
    return sorted((l for l in lessons if l.weekday == weekday), key=lambda l: l.slot)


def group_by_weekday(lessons: Iterable[Lesson]) -> dict[int, list[Lesson]]:
    grouped: dict[int, list[Lesson]] = {}
    for lesson in lessons:
        grouped.setdefault(lesson.weekday, []).append(lesson)
    for day_lessons in grouped.values():
        day_lessons.sort(key=lambda l: l.slot)
    return grouped


def _bell_by_slot(bells: Sequence[Bell], slot: int) -> Bell | None:
    for bell in bells:
        if bell.number == slot:
            return bell
    return None


def format_day(lessons: Sequence[Lesson], bells: Sequence[Bell]) -> str:
    if not lessons:
        return "Уроков нет."
    lines = []
    for lesson in sorted(lessons, key=lambda l: l.slot):
        bell = _bell_by_slot(bells, lesson.slot)
        time_part = f"{format_time(bell.start)}–{format_time(bell.end)} " if bell else ""
        line = f"{lesson.slot}. {time_part}{lesson.subject}"
        extra = ", ".join(part for part in (lesson.room, lesson.teacher) if part)
        if extra:
            line += f" ({extra})"
        lines.append(line)
    return "\n".join(lines)


def format_week(grouped: dict[int, list[Lesson]], bells: Sequence[Bell]) -> str:
    blocks = []
    for weekday in range(7):
        day_lessons = grouped.get(weekday)
        if not day_lessons:
            continue
        blocks.append(f"{WEEKDAYS_FULL[weekday].capitalize()}\n{format_day(day_lessons, bells)}")
    return "\n\n".join(blocks) if blocks else "Расписание пока пустое."
