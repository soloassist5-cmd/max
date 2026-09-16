from datetime import time

from maxbot.domain.bells import DEFAULT_BELLS, Bell, Phase, current_state, parse_bells


def test_current_state_before_lessons():
    state = current_state(DEFAULT_BELLS, time(7, 0))
    assert state.phase == Phase.BEFORE
    assert state.upcoming == DEFAULT_BELLS[0]
    assert state.minutes_left == 90


def test_current_state_during_lesson():
    state = current_state(DEFAULT_BELLS, time(8, 40))
    assert state.phase == Phase.LESSON
    assert state.current == DEFAULT_BELLS[0]
    assert state.minutes_left == 35


def test_current_state_during_break():
    state = current_state(DEFAULT_BELLS, time(9, 20))
    assert state.phase == Phase.BREAK
    assert state.current == DEFAULT_BELLS[0]
    assert state.upcoming == DEFAULT_BELLS[1]
    assert state.minutes_left == 5


def test_current_state_after_lessons():
    state = current_state(DEFAULT_BELLS, time(20, 0))
    assert state.phase == Phase.AFTER
    assert state.current == DEFAULT_BELLS[-1]


def test_current_state_empty_bells():
    state = current_state([], time(12, 0))
    assert state.phase == Phase.AFTER
    assert state.minutes_left == 0


def test_parse_bells_with_numbers():
    parsed = parse_bells("1. 8:30-9:15\n2. 9:25-10:10")
    assert parsed == [Bell(1, time(8, 30), time(9, 15)), Bell(2, time(9, 25), time(10, 10))]


def test_parse_bells_without_numbers_uses_order():
    parsed = parse_bells("8:30-9:15\n9:25-10:10")
    assert [bell.number for bell in parsed] == [1, 2]


def test_parse_bells_skips_bad_lines():
    parsed = parse_bells("1. 8:30-9:15\nчто-то не то\n2. 9:25-10:10\n3. 10:00-9:00")
    assert len(parsed) == 2
