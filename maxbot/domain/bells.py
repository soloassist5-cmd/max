from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import time
from enum import Enum
from typing import Iterable, Sequence

from .dates import format_time, parse_time


@dataclass(frozen=True, slots=True)
class Bell:
    number: int
    start: time
    end: time

    @property
    def duration_minutes(self) -> int:
        return _minutes(self.end) - _minutes(self.start)

    def __str__(self) -> str:
        return f"{self.number}. {format_time(self.start)}–{format_time(self.end)}"


DEFAULT_BELLS: tuple[Bell, ...] = (
    Bell(1, time(8, 30), time(9, 15)),
    Bell(2, time(9, 25), time(10, 10)),
    Bell(3, time(10, 25), time(11, 10)),
    Bell(4, time(11, 25), time(12, 10)),
    Bell(5, time(12, 25), time(13, 10)),
    Bell(6, time(13, 20), time(14, 5)),
    Bell(7, time(14, 15), time(15, 0)),
    Bell(8, time(15, 10), time(15, 55)),
)


class Phase(str, Enum):
    BEFORE = "before"
    LESSON = "lesson"
    BREAK = "break"
    AFTER = "after"


@dataclass(frozen=True, slots=True)
class BellState:
    phase: Phase
    minutes_left: int
    current: Bell | None = None
    upcoming: Bell | None = None


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def current_state(bells: Sequence[Bell], moment: time) -> BellState:
    if not bells:
        return BellState(Phase.AFTER, 0)

    ordered = sorted(bells, key=lambda bell: _minutes(bell.start))
    point = _minutes(moment)

    if point < _minutes(ordered[0].start):
        return BellState(Phase.BEFORE, _minutes(ordered[0].start) - point, upcoming=ordered[0])

    for index, bell in enumerate(ordered):
        start, end = _minutes(bell.start), _minutes(bell.end)
        following = ordered[index + 1] if index + 1 < len(ordered) else None
        if start <= point < end:
            return BellState(Phase.LESSON, end - point, current=bell, upcoming=following)
        if point >= end and following is not None and point < _minutes(following.start):
            return BellState(Phase.BREAK, _minutes(following.start) - point, current=bell, upcoming=following)

    return BellState(Phase.AFTER, 0, current=ordered[-1])


def parse_bells(text: str) -> list[Bell]:
    """Строки вида «1. 8:30-9:15» или «8.30—9.15», номер можно не указывать."""
    bells: list[Bell] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        number: int | None = None
        match = re.match(r"^(\d{1,2})\s*[.)]\s*(.+)$", line)
        if match:
            number = int(match.group(1))
            line = match.group(2).strip()
        parts = re.split(r"\s*[-–—]\s*", line)
        if len(parts) != 2:
            continue
        start, end = parse_time(parts[0]), parse_time(parts[1])
        if start is None or end is None or _minutes(end) <= _minutes(start):
            continue
        bells.append(Bell(number or len(bells) + 1, start, end))
    return bells


def format_bells(bells: Iterable[Bell]) -> str:
    lines = [str(bell) for bell in sorted(bells, key=lambda bell: bell.number)]
    return "\n".join(lines) if lines else "Расписание звонков не задано."
