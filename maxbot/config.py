from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_API_BASE = "https://platform-api2.max.ru"
DEFAULT_TZ_OFFSET = 3  # Москва


class ConfigError(RuntimeError):
    pass


def load_dotenv(path: str | Path = ".env") -> None:
    file = Path(path)
    if not file.is_file():
        return
    for raw_line in file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            continue
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} должен быть числом, получено {raw!r}") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if not raw:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "да"}


@dataclass(slots=True)
class Config:
    token: str
    api_base: str = DEFAULT_API_BASE
    database_path: str = "school_bot.db"
    ca_bundle: str | None = None

    mode: str = "polling"
    webhook_url: str = ""
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8080
    webhook_path: str = "/max/webhook"

    default_tz_offset: int = DEFAULT_TZ_OFFSET
    morning_digest_at: str = "07:30"
    evening_digest_at: str = "20:00"
    reminders_enabled: bool = True

    poll_timeout: int = 30
    poll_limit: int = 100

    gigachat_auth_key: str = ""
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat"
    gigachat_ca_bundle: str | None = None
    gigachat_verify_ssl: bool = True

    @property
    def ai_enabled(self) -> bool:
        return bool(self.gigachat_auth_key)

    @classmethod
    def from_env(cls, *, dotenv: str | Path = ".env") -> "Config":
        load_dotenv(dotenv)
        token = os.getenv("MAX_BOT_TOKEN", "").strip()
        if not token:
            raise ConfigError(
                "Не задан MAX_BOT_TOKEN. Токен выдаётся в MAX при создании бота, "
                "положите его в .env (см. .env.example)."
            )
        mode = os.getenv("MAX_MODE", "polling").strip().lower()
        if mode not in {"polling", "webhook"}:
            raise ConfigError(f"MAX_MODE должен быть polling или webhook, получено {mode!r}")

        config = cls(
            token=token,
            api_base=os.getenv("MAX_API_BASE", DEFAULT_API_BASE).rstrip("/"),
            database_path=os.getenv("MAX_DB_PATH", "school_bot.db"),
            ca_bundle=os.getenv("MAX_CA_BUNDLE") or None,
            mode=mode,
            webhook_url=os.getenv("MAX_WEBHOOK_URL", "").strip(),
            webhook_host=os.getenv("MAX_WEBHOOK_HOST", "0.0.0.0"),
            webhook_port=_env_int("MAX_WEBHOOK_PORT", 8080),
            webhook_path=os.getenv("MAX_WEBHOOK_PATH", "/max/webhook"),
            default_tz_offset=_env_int("MAX_TZ_OFFSET", DEFAULT_TZ_OFFSET),
            morning_digest_at=os.getenv("MAX_MORNING_DIGEST", "07:30"),
            evening_digest_at=os.getenv("MAX_EVENING_DIGEST", "20:00"),
            reminders_enabled=_env_bool("MAX_REMINDERS", True),
            poll_timeout=_env_int("MAX_POLL_TIMEOUT", 30),
            poll_limit=_env_int("MAX_POLL_LIMIT", 100),
            gigachat_auth_key=os.getenv("GIGACHAT_AUTH_KEY", "").strip(),
            gigachat_scope=os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS").strip(),
            gigachat_model=os.getenv("GIGACHAT_MODEL", "GigaChat").strip(),
            # сертификат Минцифры нужен обоим сервисам, поэтому по умолчанию берём тот же
            gigachat_ca_bundle=os.getenv("GIGACHAT_CA_BUNDLE") or os.getenv("MAX_CA_BUNDLE") or None,
            gigachat_verify_ssl=_env_bool("GIGACHAT_VERIFY_SSL", True),
        )
        if config.mode == "webhook" and not config.webhook_url:
            raise ConfigError("Для MAX_MODE=webhook нужен MAX_WEBHOOK_URL (https)")
        if config.webhook_url and not config.webhook_url.startswith("https://"):
            raise ConfigError("MAX_WEBHOOK_URL должен быть https — MAX не принимает http")
        return config
