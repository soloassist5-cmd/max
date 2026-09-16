from __future__ import annotations

from typing import Any, Iterable, Sequence

MAX_ROWS = 30
MAX_BUTTONS = 210
MAX_BUTTONS_PER_ROW = 7
MAX_WIDE_BUTTONS_PER_ROW = 3

WIDE_BUTTON_TYPES = frozenset({"link", "open_app", "request_contact", "request_geo_location"})

INTENT_DEFAULT = "default"
INTENT_POSITIVE = "positive"
INTENT_NEGATIVE = "negative"


class KeyboardError(ValueError):
    pass


Button = dict[str, Any]
Row = list[Button]


def callback(text: str, payload: str, *, intent: str = INTENT_DEFAULT) -> Button:
    if not text:
        raise KeyboardError("У кнопки должен быть текст")
    if not payload:
        raise KeyboardError(f"У кнопки {text!r} должен быть payload")
    button: Button = {"type": "callback", "text": text, "payload": payload}
    if intent != INTENT_DEFAULT:
        button["intent"] = intent
    return button


def link(text: str, url: str) -> Button:
    if len(url) > 2048:
        raise KeyboardError("Ссылка в кнопке не может быть длиннее 2048 символов")
    return {"type": "link", "text": text, "url": url}


def message(text: str) -> Button:
    return {"type": "message", "text": text}


def clipboard(text: str, payload: str) -> Button:
    return {"type": "clipboard", "text": text, "payload": payload}


def request_contact(text: str = "Поделиться контактом") -> Button:
    return {"type": "request_contact", "text": text}


def validate(rows: Sequence[Sequence[Button]]) -> None:
    if len(rows) > MAX_ROWS:
        raise KeyboardError(f"Не больше {MAX_ROWS} рядов, получено {len(rows)}")
    total = sum(len(row) for row in rows)
    if total > MAX_BUTTONS:
        raise KeyboardError(f"Не больше {MAX_BUTTONS} кнопок всего, получено {total}")
    for index, row in enumerate(rows, start=1):
        has_wide = any(button.get("type") in WIDE_BUTTON_TYPES for button in row)
        limit = MAX_WIDE_BUTTONS_PER_ROW if has_wide else MAX_BUTTONS_PER_ROW
        if len(row) > limit:
            raise KeyboardError(f"В ряду {index} не больше {limit} кнопок, получено {len(row)}")


def keyboard(*rows: Sequence[Button]) -> dict[str, Any]:
    clean: list[Row] = [list(row) for row in rows if row]
    validate(clean)
    return {"type": "inline_keyboard", "payload": {"buttons": clean}}


def grid(buttons: Iterable[Button], *, columns: int = 2) -> list[Row]:
    if columns < 1:
        raise KeyboardError("columns должен быть положительным")
    items = list(buttons)
    return [items[i : i + columns] for i in range(0, len(items), columns)]
