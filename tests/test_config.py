import pytest

from maxbot.config import Config, ConfigError


def test_from_env_requires_token(monkeypatch, tmp_path):
    monkeypatch.delenv("MAX_BOT_TOKEN", raising=False)
    with pytest.raises(ConfigError):
        Config.from_env(dotenv=tmp_path / "missing.env")


def test_from_env_reads_token_and_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("MAX_BOT_TOKEN", "secret")
    for name in ("MAX_MODE", "MAX_WEBHOOK_URL", "MAX_API_BASE", "MAX_DB_PATH"):
        monkeypatch.delenv(name, raising=False)
    config = Config.from_env(dotenv=tmp_path / "missing.env")
    assert config.token == "secret"
    assert config.mode == "polling"
    assert config.api_base == "https://platform-api2.max.ru"
    assert config.default_tz_offset == 3


def test_from_env_rejects_unknown_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("MAX_BOT_TOKEN", "secret")
    monkeypatch.setenv("MAX_MODE", "carrier-pigeon")
    with pytest.raises(ConfigError):
        Config.from_env(dotenv=tmp_path / "missing.env")


def test_webhook_mode_requires_url(monkeypatch, tmp_path):
    monkeypatch.setenv("MAX_BOT_TOKEN", "secret")
    monkeypatch.setenv("MAX_MODE", "webhook")
    monkeypatch.delenv("MAX_WEBHOOK_URL", raising=False)
    with pytest.raises(ConfigError):
        Config.from_env(dotenv=tmp_path / "missing.env")


def test_webhook_url_must_be_https(monkeypatch, tmp_path):
    monkeypatch.setenv("MAX_BOT_TOKEN", "secret")
    monkeypatch.setenv("MAX_MODE", "webhook")
    monkeypatch.setenv("MAX_WEBHOOK_URL", "http://example.com/webhook")
    with pytest.raises(ConfigError):
        Config.from_env(dotenv=tmp_path / "missing.env")


def test_loads_values_from_dotenv_file(tmp_path, monkeypatch):
    monkeypatch.delenv("MAX_BOT_TOKEN", raising=False)
    monkeypatch.delenv("MAX_TZ_OFFSET", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("MAX_BOT_TOKEN=from-file\nMAX_TZ_OFFSET=5\n", encoding="utf-8")
    config = Config.from_env(dotenv=env_file)
    assert config.token == "from-file"
    assert config.default_tz_offset == 5
