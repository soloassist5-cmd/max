from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from .dates import format_relative_date


@dataclass(frozen=True, slots=True)
class Homework:
    id: int
    subject: str
    due_date: date
    text: str
    created_by: int
    created_at: datetime
    done: bool = False


def split_pending_done(items: Iterable[Homework]) -> tuple[list[Homework], list[Homework]]:
    items = list(items)
    return [hw for hw in items if not hw.done], [hw for hw in items if hw.done]


def format_list(items: Iterable[Homework], *, today_date: date) -> str:
    ordered = sorted(items, key=lambda hw: (hw.due_date, hw.subject.lower()))
    if not ordered:
        return "Домашних заданий не найдено."
    lines: list[str] = []
    current_date: date | None = None
    for hw in ordered:
        if hw.due_date != current_date:
            current_date = hw.due_date
            label = format_relative_date(current_date, today_date=today_date)
            lines.append(f"\n{label}:" if lines else f"{label}:")
        mark = "✅" if hw.done else "▫️"
        overdue = " (просрочено)" if hw.due_date < today_date and not hw.done else ""
        lines.append(f"{mark} #{hw.id} {hw.subject} — {hw.text}{overdue}")
    return "\n".join(lines).strip()
