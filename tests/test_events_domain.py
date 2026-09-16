from datetime import date, time

from maxbot.domain.events import Event, days_left, format_event, format_list, upcoming


def _event(id_, title, event_date, event_time=None, kind="Контрольная"):
    return Event(id=id_, title=title, kind=kind, event_date=event_date, event_time=event_time, created_by=1)


def test_days_left():
    today = date(2026, 9, 16)
    assert days_left(_event(1, "Х", date(2026, 9, 18)), today_date=today) == 2


def test_upcoming_filters_past_and_sorts():
    today = date(2026, 9, 16)
    events = [
        _event(1, "Прошедшее", date(2026, 9, 10)),
        _event(2, "Позже", date(2026, 9, 20)),
        _event(3, "Раньше", date(2026, 9, 17)),
    ]
    result = upcoming(events, today_date=today)
    assert [e.id for e in result] == [3, 2]


def test_upcoming_sorts_same_day_by_time():
    today = date(2026, 9, 16)
    events = [
        _event(1, "Позже", today, event_time=time(14, 0)),
        _event(2, "Раньше", today, event_time=time(9, 0)),
    ]
    result = upcoming(events, today_date=today)
    assert [e.id for e in result] == [2, 1]


def test_format_event_today_has_exclamation():
    today = date(2026, 9, 16)
    text = format_event(_event(1, "Контрольная по химии", today), today_date=today)
    assert "сегодня!" in text
    assert text.startswith("#1 Контрольная: Контрольная по химии")


def test_format_event_with_time_and_countdown():
    today = date(2026, 9, 16)
    text = format_event(_event(1, "ОГЭ", date(2026, 9, 18), event_time=time(10, 0)), today_date=today)
    assert "в 10:00" in text
    assert "через 2 дня" in text


def test_format_list_empty():
    assert format_list([], today_date=date(2026, 9, 16)) == "Ближайших событий нет."
