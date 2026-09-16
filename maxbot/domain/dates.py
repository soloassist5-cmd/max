from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone

WEEKDAYS_FULL = (
    "понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье",
)
WEEKDAYS_PREPOSITIONAL = (
    "понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье",
)
WEEKDAYS_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")

MONTHS_GENITIVE = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)

_WEEKDAY_ALIASES: dict[str, int] = {}
for _index, _full in enumerate(WEEKDAYS_FULL):
    _WEEKDAY_ALIASES[_full] = _index
    _WEEKDAY_ALIASES[WEEKDAYS_SHORT[_index].lower()] = _index
    _WEEKDAY_ALIASES[WEEKDAYS_PREPOSITIONAL[_index]] = _index
_WEEKDAY_ALIASES.update({
    "пон": 0, "понедельника": 0,
    "вт": 1, "вторника": 1,
    "ср": 2, "среды": 2,
    "чт": 3, "четверга": 3,
    "пт": 4, "пятницы": 4,
    "сб": 5, "субботы": 5,
    "вс": 6, "воскресенья": 6,
})

_MONTH_ALIASES: dict[str, int] = {}
for _index, _month in enumerate(MONTHS_GENITIVE, start=1):
    _MONTH_ALIASES[_month] = _index
    _MONTH_ALIASES[_month[:3]] = _index
_MONTH_ALIASES.update({
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6,
    "июль": 7, "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12,
})

_NUMERIC_DATE = re.compile(r"^(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?$")
_TEXT_DATE = re.compile(r"^(\d{1,2})\s+([а-яё]+)$")
_TIME_RE = re.compile(r"^(\d{1,2})[:.](\d{2})$")


def tz(offset_hours: int) -> timezone:
    return timezone(timedelta(hours=offset_hours))


def now(offset_hours: int) -> datetime:
    return datetime.now(tz(offset_hours))


def today(offset_hours: int) -> date:
    return now(offset_hours).date()


def parse_time(text: str) -> time | None:
    match = _TIME_RE.match(text.strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def parse_weekday(text: str) -> int | None:
    cleaned = text.strip().lower().replace("ё", "е").rstrip(":.,")
    cleaned = re.sub(r"^(в|во)\s+", "", cleaned)
    for alias, index in _WEEKDAY_ALIASES.items():
        if alias.replace("ё", "е") == cleaned:
            return index
    return None


def parse_date(text: str, *, today_date: date) -> date | None:
    """Поддерживает: сегодня/завтра/послезавтра, день недели, 17.09[.2026], 17 сентября."""
    cleaned = text.strip().lower().replace("ё", "е")
    if not cleaned:
        return None

    if cleaned in {"сегодня", "сегодня же"}:
        return today_date
    if cleaned == "завтра":
        return today_date + timedelta(days=1)
    if cleaned == "послезавтра":
        return today_date + timedelta(days=2)

    weekday = parse_weekday(cleaned)
    if weekday is not None:
        return next_weekday(today_date, weekday)

    match = _NUMERIC_DATE.match(cleaned)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        year_raw = match.group(3)
        if year_raw is None:
            return _nearest_year(today_date, month, day)
        year = int(year_raw)
        if year < 100:
            year += 2000
        return _safe_date(year, month, day)

    match = _TEXT_DATE.match(cleaned)
    if match:
        month = _MONTH_ALIASES.get(match.group(2))
        if month:
            return _nearest_year(today_date, month, int(match.group(1)))
    return None


def next_weekday(from_date: date, weekday: int) -> date:
    delta = (weekday - from_date.weekday()) % 7
    return from_date + timedelta(days=delta or 7)


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _nearest_year(today_date: date, month: int, day: int) -> date | None:
    candidate = _safe_date(today_date.year, month, day)
    if candidate is None:
        return None
    if (today_date - candidate).days > 180:
        return _safe_date(today_date.year + 1, month, day)
    return candidate


def format_date(value: date, *, with_weekday: bool = True) -> str:
    body = f"{value.day} {MONTHS_GENITIVE[value.month - 1]}"
    return f"{WEEKDAYS_FULL[value.weekday()]}, {body}" if with_weekday else body


def format_relative_date(value: date, *, today_date: date) -> str:
    delta = (value - today_date).days
    if delta == 0:
        return "сегодня"
    if delta == 1:
        return "завтра"
    if delta == 2:
        return "послезавтра"
    if delta == -1:
        return "вчера"
    return format_date(value)


def format_time(value: time) -> str:
    return f"{value.hour:02d}:{value.minute:02d}"


def plural(number: int, one: str, few: str, many: str) -> str:
    abs_number = abs(number) % 100
    if 11 <= abs_number <= 14:
        return many
    last = abs_number % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many


def minutes_phrase(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} {plural(minutes, 'минута', 'минуты', 'минут')}"
    hours, rest = divmod(minutes, 60)
    text = f"{hours} {plural(hours, 'час', 'часа', 'часов')}"
    if rest:
        text += f" {rest} {plural(rest, 'минута', 'минуты', 'минут')}"
    return text
