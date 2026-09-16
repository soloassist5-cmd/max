from maxbot.api.types import Update


def test_message_created_in_group_chat():
    update = Update.parse({
        "update_type": "message_created",
        "timestamp": 1,
        "message": {
            "sender": {"user_id": 5, "name": "Аня Иванова"},
            "recipient": {"chat_id": 100, "chat_type": "chat"},
            "body": {"mid": "m1", "seq": 1, "text": "привет"},
        },
    })
    assert update.chat_id == 100
    assert update.chat_type == "chat"
    assert update.is_dialog is False
    assert update.effective_chat_type == "chat"
    assert update.user_id == 5
    assert update.user.name == "Аня Иванова"
    assert update.user.first_name == "Аня"
    assert update.text == "привет"
    assert update.message_id == "m1"


def test_message_created_in_dialog():
    update = Update.parse({
        "update_type": "message_created",
        "timestamp": 1,
        "message": {
            "sender": {"user_id": 5, "name": "Аня"},
            "recipient": {"user_id": 777, "chat_type": "dialog"},
            "body": {"mid": "m1", "seq": 1, "text": "привет"},
        },
    })
    assert update.chat_type == "dialog"
    assert update.is_dialog is True
    assert update.effective_chat_type == "dialog"
    assert update.user_id == 5


def test_message_callback_reads_button_payload_and_pressing_user():
    update = Update.parse({
        "update_type": "message_callback",
        "timestamp": 1,
        "callback": {
            "timestamp": 1,
            "callback_id": "cb42",
            "payload": "hw:done:3",
            "user": {"user_id": 9, "name": "Пётр"},
        },
        "message": {
            "recipient": {"chat_id": 55, "chat_type": "chat"},
            "body": {"mid": "m2", "seq": 2, "text": ""},
        },
    })
    assert update.callback_id == "cb42"
    assert update.payload == "hw:done:3"
    assert update.user_id == 9
    assert update.chat_id == 55
    assert update.is_dialog is False


def test_bot_started_is_always_dialog():
    update = Update.parse({
        "update_type": "bot_started",
        "timestamp": 1,
        "chat_id": 777,
        "user": {"user_id": 5, "name": "Аня"},
        "payload": "invite42",
    })
    assert update.is_dialog is True
    assert update.effective_chat_type == "dialog"
    assert update.chat_id == 777
    assert update.user_id == 5
    assert update.payload == "invite42"


def test_bot_added_to_chat_is_not_dialog():
    update = Update.parse({
        "update_type": "bot_added",
        "timestamp": 1,
        "chat_id": 100,
        "user": {"user_id": 5, "name": "Аня"},
        "is_channel": False,
    })
    assert update.is_dialog is False
    assert update.effective_chat_type == "chat"
    assert update.chat_id == 100


def test_bot_added_to_channel():
    update = Update.parse({
        "update_type": "bot_added",
        "timestamp": 1,
        "chat_id": 100,
        "user": {"user_id": 5, "name": "Аня"},
        "is_channel": True,
    })
    assert update.effective_chat_type == "channel"


def test_user_parse_missing_data_returns_none():
    from maxbot.api.types import User

    assert User.parse(None) is None
    assert User.parse({}) is None


def test_user_first_name_fallback():
    from maxbot.api.types import User

    assert User(user_id=1, name="").first_name == "друг"
    assert User(user_id=1, name="Мария Смирнова").first_name == "Мария"
