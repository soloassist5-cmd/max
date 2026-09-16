import pytest

from maxbot.api import keyboard as kb


def test_callback_button_requires_payload():
    with pytest.raises(kb.KeyboardError):
        kb.callback("Кнопка", "")


def test_link_button_url_length_limit():
    with pytest.raises(kb.KeyboardError):
        kb.link("Сайт", "https://example.com/" + "a" * 2048)


def test_keyboard_row_limit_for_regular_buttons():
    row = [kb.callback(str(i), str(i)) for i in range(8)]
    with pytest.raises(kb.KeyboardError):
        kb.keyboard(row)


def test_keyboard_row_limit_for_wide_buttons():
    row = [kb.link(str(i), "https://example.com") for i in range(4)]
    with pytest.raises(kb.KeyboardError):
        kb.keyboard(row)


def test_keyboard_total_rows_limit():
    rows = [[kb.callback("x", "x")] for _ in range(31)]
    with pytest.raises(kb.KeyboardError):
        kb.keyboard(*rows)


def test_keyboard_drops_empty_rows():
    result = kb.keyboard([], [kb.callback("A", "a")], [])
    assert result["payload"]["buttons"] == [[{"type": "callback", "text": "A", "payload": "a"}]]


def test_grid_splits_into_columns():
    buttons = [kb.callback(str(i), str(i)) for i in range(5)]
    rows = kb.grid(buttons, columns=2)
    assert [len(row) for row in rows] == [2, 2, 1]


def test_callback_intent_included_only_when_not_default():
    plain = kb.callback("Ок", "ok")
    positive = kb.callback("Ок", "ok", intent=kb.INTENT_POSITIVE)
    assert "intent" not in plain
    assert positive["intent"] == "positive"
