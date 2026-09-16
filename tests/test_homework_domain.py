from datetime import date, datetime

from maxbot.domain.homework import Homework, format_list, split_pending_done


def _hw(id_, subject, due_date, done=False):
    return Homework(id=id_, subject=subject, due_date=due_date, text="сделать", created_by=1,
                     created_at=datetime(2026, 9, 1), done=done)


def test_split_pending_done():
    items = [_hw(1, "А", date(2026, 9, 20)), _hw(2, "Б", date(2026, 9, 21), done=True)]
    pending, done = split_pending_done(items)
    assert [hw.id for hw in pending] == [1]
    assert [hw.id for hw in done] == [2]


def test_format_list_empty():
    assert format_list([], today_date=date(2026, 9, 16)) == "Домашних заданий не найдено."


def test_format_list_groups_by_date_and_marks_overdue():
    today = date(2026, 9, 16)
    items = [
        _hw(1, "Физика", date(2026, 9, 15)),  # просрочено
        _hw(2, "Алгебра", date(2026, 9, 16), done=True),
    ]
    text = format_list(items, today_date=today)
    assert "вчера:" in text
    assert "(просрочено)" in text
    assert "✅ #2 Алгебра" in text


def test_format_list_sorted_within_same_date_by_subject():
    today = date(2026, 9, 16)
    items = [_hw(1, "Русский", today), _hw(2, "Алгебра", today)]
    text = format_list(items, today_date=today)
    assert text.index("Алгебра") < text.index("Русский")
