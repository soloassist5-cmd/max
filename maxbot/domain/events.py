from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from typing import Iterable

from .dates import format_relative_date, plural


@dataclass(frozen=True, slots=True)
class Event:
    id: int
    title: str
    kind: str
    event_date: date
    event_time: time | None
    created_by: int


def days_left(event: Event, *, today_date: date) -> int:
    return (event.event_date - today_date).days


def upcoming(events: Iterable[Event], *, today_date: date) -> list[Event]:
    items = [e for e in events if e.event_date >= today_date]
    items.sort(key=lambda e: (e.event_date, e.event_time or time.min))
    return items


def format_event(event: Event, *, today_date: date) -> str:
    when = format_relative_date(event.event_date, today_date=today_date)
    if event.event_time:
        when += f" в {event.event_time.hour:02d}:{event.event_time.minute:02d}"
    prefix = f"{event.kind}: " if event.kind else ""

    left = days_left(event, today_date=today_date)
    countdown = ""
    if left == 0:
        countdown = " — сегодня!"
    elif left > 0:
        countdown = f" (через {left} {plural(left, 'день', 'дня', 'дней')})"

    return f"#{event.id} {prefix}{event.title} — {when}{countdown}"


def format_list(events: Iterable[Event], *, today_date: date) -> str:
    items = upcoming(events, today_date=today_date)
    if not items:
        return "Ближайших событий нет."
    return "\n".join(format_event(e, today_date=today_date) for e in items)
