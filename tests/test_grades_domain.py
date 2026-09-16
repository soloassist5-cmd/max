from datetime import datetime

from maxbot.domain.grades import Grade, average, format_grades, group_by_subject


def _grade(id_, subject, value):
    return Grade(id=id_, subject=subject, value=value, note="", created_at=datetime(2026, 9, id_))


def test_average_empty():
    assert average([]) == 0.0


def test_average_computes_mean():
    grades = [_grade(1, "Физика", 4), _grade(2, "Физика", 5)]
    assert average(grades) == 4.5


def test_group_by_subject_sorted_by_date():
    grades = [_grade(2, "Физика", 5), _grade(1, "Физика", 4)]
    grouped = group_by_subject(grades)
    assert [g.id for g in grouped["Физика"]] == [1, 2]


def test_format_grades_empty():
    assert format_grades([]) == "Оценок пока нет."


def test_format_grades_shows_per_subject_and_overall_average():
    grades = [_grade(1, "Алгебра", 5), _grade(2, "Алгебра", 3), _grade(3, "Физика", 4)]
    text = format_grades(grades)
    assert "Алгебра: 5 3 (среднее 4.00)" in text
    assert "Физика: 4 (среднее 4.00)" in text
    assert "Общий средний балл: 4.00" in text
