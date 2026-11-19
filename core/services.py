"""Бизнес-сценарии командного списка задач."""

from datetime import datetime, timezone

from core.models import (
    DEFAULT_CATEGORY,
    DONE_STATUS,
    CsvExport,
    Task,
    validate_task_status,
)
from core.ports import TaskExporter, TaskRepository


class TaskService:
    """Координирует работу с задачами через инфраструктурные порты."""

    def __init__(self, repository: TaskRepository, exporter: TaskExporter) -> None:
        """Сохраняет хранилище и CSV-экспортёр для бизнес-сценариев."""
        self._repository = repository
        self._exporter = exporter

    async def add_task(
        self,
        text: str,
        user: str,
        category: str = DEFAULT_CATEGORY,
    ) -> Task:
        """Создаёт задачу в UTC и делегирует атомарное сохранение репозиторию."""
        task = Task(
            id=None,
            text=text,
            user=user,
            created_at=datetime.now(timezone.utc),
            category=category,
        )
        return await self._repository.add_task(task)

    async def get_all_tasks(self) -> list[Task]:
        """Возвращает все задачи общего списка."""
        return await self._repository.get_all()

    async def mark_task_done(self, task_id: int) -> bool:
        """Отмечает задачу выполненной; возвращает False, если её нет."""
        return await self.update_task_status(task_id, DONE_STATUS)

    async def update_task_status(self, task_id: int, status: str) -> bool:
        """Проверяет статус и меняет его; возвращает False, если задача не найдена."""
        clean_status = validate_task_status(status)
        return await self._repository.update_status(task_id, clean_status)

    async def export_tasks_csv(self) -> CsvExport:
        """Формирует CSV-файл и запоминает количество выгруженных задач."""
        tasks = await self.get_all_tasks()
        return CsvExport(
            content=self._exporter.export(tasks),
            task_count=len(tasks),
        )

