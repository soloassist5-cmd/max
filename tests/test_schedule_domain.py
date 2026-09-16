from datetime import time

from maxbot.domain.bells import Bell
from maxbot.domain.schedule import Lesson, by_weekday, format_day, format_week, group_by_weekday


def test_by_weekday_filters_and_sorts():
    lessons = [
        Lesson(1, weekday=0, slot=2, subject="Физика"),
        Lesson(2, weekday=0, slot=1, subject="Алгебра"),
        Lesson(3, weekday=1, slot=1, subject="История"),
    ]
    monday = by_weekday(lessons, 0)
    assert [lesson.subject for lesson in monday] == ["Алгебра", "Физика"]


def test_format_day_empty():
    assert format_day([], []) == "Уроков нет."


def test_format_day_includes_time_and_room():
    bells = [Bell(1, time(8, 30), time(9, 15))]
    lessons = [Lesson(1, weekday=0, slot=1, subject="Химия", room="204")]
    text = format_day(lessons, bells)
    assert text == "1. 08:30–09:15 Химия (204)"


def test_format_day_without_matching_bell():
    lessons = [Lesson(1, weekday=0, slot=5, subject="Труд")]
    assert format_day(lessons, []) == "5. Труд"


def test_group_by_weekday_sorts_each_day():
    lessons = [
        Lesson(1, weekday=2, slot=3, subject="Б"),
        Lesson(2, weekday=2, slot=1, subject="А"),
    ]
    grouped = group_by_weekday(lessons)
    assert [lesson.subject for lesson in grouped[2]] == ["А", "Б"]


def test_format_week_skips_empty_days():
    lessons = [Lesson(1, weekday=4, slot=1, subject="Физра")]
    grouped = group_by_weekday(lessons)
    text = format_week(grouped, [])
    assert text == "Пятница\n1. Физра"


def test_format_week_empty():
    assert format_week({}, []) == "Расписание пока пустое."
