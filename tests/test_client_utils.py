from maxbot.api.client import MAX_TEXT_LENGTH, split_text
from maxbot.api.errors import MaxApiError


def test_split_text_short_text_returned_as_is():
    assert split_text("привет") == ["привет"]


def test_split_text_splits_long_text_by_lines():
    line = "a" * 100
    text = "\n".join([line] * 60)  # длиннее MAX_TEXT_LENGTH
    parts = split_text(text, limit=500)
    assert all(len(part) <= 500 for part in parts)
    assert "".join(parts).replace("⁣", "").count("a") == 6000


def test_split_text_breaks_single_huge_line():
    text = "a" * (MAX_TEXT_LENGTH + 10)
    parts = split_text(text)
    assert len(parts) == 2
    assert all(len(part) <= MAX_TEXT_LENGTH for part in parts)


def test_split_text_never_returns_empty_list():
    assert split_text("") == [""]


def test_max_api_error_flags():
    assert MaxApiError(401).is_auth_error is True
    assert MaxApiError(429).is_rate_limited is True
    assert MaxApiError(429).is_retriable is True
    assert MaxApiError(503).is_retriable is True
    assert MaxApiError(400).is_retriable is False
