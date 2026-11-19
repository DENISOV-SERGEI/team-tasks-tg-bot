"""Доменная модель задачи."""

from dataclasses import dataclass
from datetime import datetime, timezone

from core.errors import (
    EmptyTaskTextError,
    InvalidTaskStatusError,
    TaskTextTooLongError,
)


MAX_TASK_TEXT_LENGTH = 3000

# Значения по умолчанию и допустимые категории задачи.
DEFAULT_CATEGORY = "Общее"
DEFAULT_STATUS = "Новая"
OLD_STATUS = "Старая"
DONE_STATUS = "Выполнена"
TASK_CATEGORIES = ("Разработка", "Дизайн", "Тестирование", "Общее")
VALID_TASK_STATUSES = (DEFAULT_STATUS, OLD_STATUS, DONE_STATUS)


def normalize_task_text(text: str) -> str:
    """Нормализует текст задачи для поиска совпадений."""
    return " ".join(text.split()).casefold()


def validate_task_status(status: str) -> str:
    """Нормализует и проверяет статус задачи."""
    if not isinstance(status, str):
        raise InvalidTaskStatusError(
            "Статус должен быть одним из: «Новая», «Старая», «Выполнена»."
        )

    clean_status = status.strip()
    if clean_status not in VALID_TASK_STATUSES:
        raise InvalidTaskStatusError(
            "Статус должен быть одним из: «Новая», «Старая», «Выполнена»."
        )
    return clean_status


@dataclass(frozen=True, slots=True)
class Task:
    """Представляет задачу общего списка команды."""

    id: int | None
    text: str
    user: str
    created_at: datetime
    category: str = DEFAULT_CATEGORY
    status: str = DEFAULT_STATUS

    def __post_init__(self) -> None:
        """Проверяет поля задачи и приводит время к UTC."""
        clean_text = self.text.strip()
        if not clean_text:
            raise EmptyTaskTextError("Текст задачи не должен быть пустым.")
        if len(clean_text) > MAX_TASK_TEXT_LENGTH:
            raise TaskTextTooLongError(
                f"Текст задачи не должен превышать {MAX_TASK_TEXT_LENGTH} символов."
            )

        clean_user = self.user.strip()
        if not clean_user:
            raise ValueError("Для задачи необходимо указать автора.")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("Время создания должно содержать часовой пояс.")

        clean_category = self.category.strip()
        if not clean_category:
            raise ValueError("Категория задачи не должна быть пустой.")

        clean_status = validate_task_status(self.status)

        object.__setattr__(self, "text", clean_text)
        object.__setattr__(self, "user", clean_user)
        object.__setattr__(self, "created_at", self.created_at.astimezone(timezone.utc))
        object.__setattr__(self, "category", clean_category)
        object.__setattr__(self, "status", clean_status)


@dataclass(frozen=True, slots=True)
class CsvExport:
    """Результат экспорта: содержимое файла и число вошедших задач."""

    content: bytes
    task_count: int
