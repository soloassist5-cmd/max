from datetime import date, time

from maxbot.domain import dates


def test_parse_relative_words():
    today = date(2026, 9, 16)  # среда
    assert dates.parse_date("сегодня", today_date=today) == today
    assert dates.parse_date("завтра", today_date=today) == date(2026, 9, 17)
    assert dates.parse_date("послезавтра", today_date=today) == date(2026, 9, 18)


def test_parse_weekday_picks_next_occurrence():
    today = date(2026, 9, 16)  # среда
    assert dates.parse_date("среда", today_date=today) == date(2026, 9, 23)
    assert dates.parse_date("пятницу", today_date=today) == date(2026, 9, 18)
    assert dates.parse_date("пн", today_date=today) == date(2026, 9, 21)


def test_parse_numeric_date_without_year_picks_nearest():
    today = date(2026, 9, 16)
    assert dates.parse_date("17.09", today_date=today) == date(2026, 9, 17)
    # начало января, названное в сентябре, — почти наверняка про следующий год
    assert dates.parse_date("5.01", today_date=today) == date(2027, 1, 5)


def test_parse_numeric_date_with_year():
    today = date(2026, 9, 16)
    assert dates.parse_date("1.9.2025", today_date=today) == date(2025, 9, 1)


def test_parse_text_date():
    today = date(2026, 9, 16)
    assert dates.parse_date("1 сентября", today_date=today) == date(2026, 9, 1)
    assert dates.parse_date("1 марта", today_date=today) == date(2027, 3, 1)


def test_parse_date_invalid_input():
    today = date(2026, 9, 16)
    assert dates.parse_date("ерунда", today_date=today) is None
    assert dates.parse_date("32.13", today_date=today) is None
    assert dates.parse_date("", today_date=today) is None


def test_parse_time():
    assert dates.parse_time("8:30") == time(8, 30)
    assert dates.parse_time("08.05") == time(8, 5)
    assert dates.parse_time("25:00") is None
    assert dates.parse_time("рано") is None


def test_format_relative_date():
    today = date(2026, 9, 16)
    assert dates.format_relative_date(today, today_date=today) == "сегодня"
    assert dates.format_relative_date(today.replace(day=17), today_date=today) == "завтра"
    assert dates.format_relative_date(today.replace(day=15), today_date=today) == "вчера"


def test_plural():
    assert dates.plural(1, "урок", "урока", "уроков") == "урок"
    assert dates.plural(2, "урок", "урока", "уроков") == "урока"
    assert dates.plural(5, "урок", "урока", "уроков") == "уроков"
    assert dates.plural(11, "урок", "урока", "уроков") == "уроков"
    assert dates.plural(21, "урок", "урока", "уроков") == "урок"


def test_minutes_phrase():
    assert dates.minutes_phrase(5) == "5 минут"
    assert dates.minutes_phrase(65) == "1 час 5 минут"
    assert dates.minutes_phrase(120) == "2 часа"
