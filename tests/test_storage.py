from datetime import date, time

import pytest

from maxbot.domain.bells import Bell
from maxbot.storage import Storage


@pytest.fixture
async def storage(tmp_path):
    db = Storage(str(tmp_path / "test.db"), default_tz_offset=3)
    await db.connect()
    yield db
    await db.close()


async def test_touch_chat_creates_row_with_defaults(storage):
    settings = await storage.get_chat_settings(42)
    assert settings.chat_id == 42
    assert settings.tz_offset == 3
    assert settings.digest_enabled is True
    assert settings.last_morning_digest is None


async def test_touch_chat_does_not_overwrite_existing_type_with_none(storage):
    await storage.touch_chat(1, chat_type="chat")
    await storage.touch_chat(1)  # без chat_type — не должно затереть
    settings = await storage.get_chat_settings(1)
    assert settings.chat_type == "chat"


async def test_update_chat_settings(storage):
    await storage.update_chat_settings(1, tz_offset=5, digest_enabled=0)
    settings = await storage.get_chat_settings(1)
    assert settings.tz_offset == 5
    assert settings.digest_enabled is False


async def test_upsert_lesson_replaces_on_same_slot(storage):
    first_id = await storage.upsert_lesson(1, weekday=0, slot=1, subject="Алгебра")
    second_id = await storage.upsert_lesson(1, weekday=0, slot=1, subject="Геометрия", room="204")
    assert first_id == second_id
    lessons = await storage.list_lessons(1)
    assert len(lessons) == 1
    assert lessons[0].subject == "Геометрия"
    assert lessons[0].room == "204"


async def test_list_lessons_ordered_by_weekday_and_slot(storage):
    await storage.upsert_lesson(1, weekday=1, slot=2, subject="Б")
    await storage.upsert_lesson(1, weekday=0, slot=1, subject="А")
    lessons = await storage.list_lessons(1)
    assert [lesson.subject for lesson in lessons] == ["А", "Б"]


async def test_remove_lesson(storage):
    lesson_id = await storage.upsert_lesson(1, weekday=0, slot=1, subject="Химия")
    assert await storage.remove_lesson(1, lesson_id) is True
    assert await storage.remove_lesson(1, lesson_id) is False
    assert await storage.list_lessons(1) == []


async def test_bells_roundtrip(storage):
    bells = [Bell(1, time(8, 30), time(9, 15)), Bell(2, time(9, 25), time(10, 10))]
    await storage.set_bells(7, bells)
    assert await storage.get_bells(7) == bells
    await storage.set_bells(7, [])
    assert await storage.get_bells(7) == []


async def test_homework_add_list_and_done_is_per_user(storage):
    hw_id = await storage.add_homework(1, "Физика", date(2026, 9, 20), "параграф 5", 10, "Аня")
    for_user_a = await storage.list_homework(1, user_id=10)
    assert for_user_a[0].done is False

    assert await storage.toggle_homework_done(hw_id, 10) is True
    for_user_a = await storage.list_homework(1, user_id=10)
    assert for_user_a[0].done is True

    for_user_b = await storage.list_homework(1, user_id=99)
    assert for_user_b[0].done is False  # у другого пользователя своя отметка

    assert await storage.toggle_homework_done(hw_id, 10) is False


async def test_homework_only_pending_filter(storage):
    done_id = await storage.add_homework(1, "А", date(2026, 9, 20), "т1", 10, "Аня")
    await storage.add_homework(1, "Б", date(2026, 9, 21), "т2", 10, "Аня")
    await storage.toggle_homework_done(done_id, 10)
    pending = await storage.list_homework(1, user_id=10, only_pending=True)
    assert [hw.subject for hw in pending] == ["Б"]


async def test_list_homework_by_date_ignores_done_state(storage):
    hw_id = await storage.add_homework(1, "А", date(2026, 9, 20), "т1", 10, "Аня")
    await storage.toggle_homework_done(hw_id, 10)
    items = await storage.list_homework_by_date(1, date(2026, 9, 20))
    assert len(items) == 1
    assert items[0].done is False


async def test_delete_homework_also_clears_done_marks(storage):
    hw_id = await storage.add_homework(1, "А", date(2026, 9, 20), "т1", 10, "Аня")
    await storage.toggle_homework_done(hw_id, 10)
    assert await storage.delete_homework(1, hw_id) is True
    assert await storage.delete_homework(1, hw_id) is False
    assert await storage.list_homework(1, user_id=10) == []


async def test_events_add_list_and_delete(storage):
    event_id = await storage.add_event(1, "Контрольная", "Математика", date(2026, 9, 20), time(10, 0), 10, "Аня")
    events = await storage.list_events(1)
    assert len(events) == 1
    assert events[0].id == event_id
    assert await storage.delete_event(1, event_id) is True
    assert await storage.list_events(1) == []


async def test_events_to_remind_and_mark_notified(storage):
    today = date(2026, 9, 16)
    tomorrow = date(2026, 9, 17)
    in_window = await storage.add_event(1, "Контрольная", "Химия", tomorrow, None, 10, "Аня")
    await storage.add_event(1, "Далеко", "История", date(2026, 10, 1), None, 10, "Аня")

    due = await storage.events_to_remind(1, today, tomorrow)
    assert [event.id for event in due] == [in_window]

    await storage.mark_event_notified(in_window)
    due_again = await storage.events_to_remind(1, today, tomorrow)
    assert due_again == []


async def test_grades_add_list_delete(storage):
    grade_id = await storage.add_grade(1, 10, "Физика", 5, "контрольная")
    grades = await storage.list_grades(1, 10)
    assert len(grades) == 1
    assert grades[0].value == 5
    assert await storage.delete_grade(1, 10, grade_id) is True
    assert await storage.list_grades(1, 10) == []


async def test_pending_action_roundtrip(storage):
    assert await storage.get_pending(1, 10) is None
    await storage.set_pending(1, 10, "add_lesson", {"step": "weekday"})
    action, data = await storage.get_pending(1, 10)
    assert action == "add_lesson"
    assert data == {"step": "weekday"}
    await storage.clear_pending(1, 10)
    assert await storage.get_pending(1, 10) is None


async def test_marker_roundtrip(storage):
    assert await storage.get_marker() is None
    await storage.set_marker(12345)
    assert await storage.get_marker() == 12345
    await storage.set_marker(67890)
    assert await storage.get_marker() == 67890
