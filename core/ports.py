"""Интерфейсы, через которые ядро обращается к инфраструктуре."""

from collections.abc import Sequence
from typing import Protocol

from core.models import Task


class TaskRepository(Protocol):
    """Описывает хранилище задач без привязки к конкретной базе данных."""

    async def add_task(self, task: Task) -> Task:
        """Атомарно сохраняет задачу или выбрасывает TaskRepositoryError."""

    async def get_all(self) -> list[Task]:
        """Возвращает все задачи или выбрасывает TaskRepositoryError."""

    async def update_status(self, task_id: int, status: str) -> bool:
        """Меняет статус или выбрасывает TaskRepositoryError при сбое хранилища."""


class TaskExporter(Protocol):
    """Описывает создание файла со списком задач."""

    def export(self, tasks: Sequence[Task]) -> bytes:
        """Возвращает содержимое CSV-файла в байтах."""
