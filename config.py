"""Загрузка конфигурации Telegram-бота из переменных окружения."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True, slots=True)
class Settings:
    """Хранит настройки, необходимые для запуска приложения."""

    bot_token: str
    database_path: Path
    proxy_url: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        """Загружает настройки из окружения и локального файла `.env`."""
        load_dotenv(PROJECT_DIR / ".env")

        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not bot_token:
            raise RuntimeError(
                "Не задан TELEGRAM_BOT_TOKEN. Создайте .env по примеру .env.example."
            )

        database_value = os.getenv("TASKS_DB_PATH", "tasks.db").strip()
        database_path = Path(database_value).expanduser()
        if not database_path.is_absolute():
            database_path = PROJECT_DIR / database_path

        # Прокси нужен только там, где Telegram недоступен напрямую.
        # Пустое значение означает обычное подключение.
        proxy_value = os.getenv("TELEGRAM_PROXY_URL", "").strip()

        return cls(
            bot_token=bot_token,
            database_path=database_path,
            proxy_url=proxy_value or None,
        )
