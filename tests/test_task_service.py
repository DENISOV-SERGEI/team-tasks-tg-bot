"""Тесты бизнес-логики и CSV-экспорта."""

import csv
import io
import unittest
from datetime import datetime, timezone

from core.errors import EmptyTaskTextError, InvalidTaskStatusError, TaskTextTooLongError
from core.models import (
    DEFAULT_STATUS,
    DONE_STATUS,
    MAX_TASK_TEXT_LENGTH,
    OLD_STATUS,
    Task,
    normalize_task_text,
)
from core.services import TaskService
from driver.csv_exporter import CsvTaskExporter


class InMemoryTaskRepository:
    """Простое хранилище для тестирования сервиса без SQLite и Telegram."""

    def __init__(self) -> None:
        self.tasks: list[Task] = []

    async def add_task(self, task: Task) -> Task:
        """Сохраняет задачу с учётом повторов для тестирования сервиса."""
        is_duplicate = any(
            normalize_task_text(existing.text) == normalize_task_text(task.text)
            for existing in self.tasks
        )
        saved = Task(
            id=len(self.tasks) + 1,
            text=task.text,
            user=task.user,
            created_at=task.created_at,
            category=task.category,
            status=OLD_STATUS if is_duplicate else DEFAULT_STATUS,
        )
        self.tasks.append(saved)
        return saved

    async def get_all(self) -> list[Task]:
        return list(self.tasks)

    async def update_status(self, task_id: int, status: str) -> bool:
        for index, task in enumerate(self.tasks):
            if task.id == task_id:
                self.tasks[index] = Task(
                    id=task.id,
                    text=task.text,
                    user=task.user,
                    created_at=task.created_at,
                    category=task.category,
                    status=status,
                )
                return True
        return False


class TaskServiceTests(unittest.IsolatedAsyncioTestCase):
    """Проверяет добавление задач и формирование CSV."""

    async def asyncSetUp(self) -> None:
        """Создаёт изолированное хранилище для каждого теста."""
        self.repository = InMemoryTaskRepository()
        self.exporter = CsvTaskExporter()
        self.service = TaskService(self.repository, self.exporter)

    async def test_add_task_trims_text_and_assigns_id(self) -> None:
        """Сервис сохраняет нормализованный текст и возвращает присвоенный ID."""
        task = await self.service.add_task("  Подготовить отчёт  ", "@sergey")

        self.assertEqual(task.id, 1)
        self.assertEqual(task.text, "Подготовить отчёт")
        self.assertEqual(task.user, "@sergey")
        self.assertEqual(task.created_at.utcoffset(), datetime.now(timezone.utc).utcoffset())

    async def test_add_task_with_category_uses_new_status(self) -> None:
        """Сервис сохраняет выбранную категорию и статус «Новая»."""
        task = await self.service.add_task(
            "Сверстать экран",
            "@designer",
            category="Дизайн",
        )

        self.assertEqual(task.category, "Дизайн")
        self.assertEqual(task.status, "Новая")
        self.assertEqual(self.repository.tasks[0].category, "Дизайн")

    async def test_task_rejects_invalid_status(self) -> None:
        """Доменная модель отклоняет пустые и неизвестные статусы."""
        for status in ("", "В работе"):
            with self.subTest(status=status):
                with self.assertRaises(InvalidTaskStatusError):
                    Task(
                        id=None,
                        text="Проверить задачу",
                        user="@sergey",
                        created_at=datetime.now(timezone.utc),
                        status=status,
                    )

        self.assertEqual(self.repository.tasks, [])

    async def test_duplicate_task_is_saved_with_old_status(self) -> None:
        """Повторный текст помечается старым независимо от регистра, пробелов и автора."""
        original = await self.service.add_task("Сверстать экран", "@designer")
        duplicate = await self.service.add_task(
            "  сверстать   ЭКРАН  ",
            "@another_user",
            category="Тестирование",
        )

        self.assertEqual(original.status, "Новая")
        self.assertEqual(duplicate.status, "Старая")
        self.assertEqual(
            [task.status for task in await self.service.get_all_tasks()],
            ["Новая", "Старая"],
        )

    async def test_mark_task_done_changes_status(self) -> None:
        """Сервис меняет статус существующей задачи на «Выполнена»."""
        task = await self.service.add_task("Закрыть задачу", "@sergey")

        updated = await self.service.mark_task_done(task.id)
        stored = (await self.service.get_all_tasks())[0]

        self.assertTrue(updated)
        self.assertEqual(stored.status, DONE_STATUS)
        self.assertFalse(await self.service.mark_task_done(9999))

    async def test_update_task_status_rejects_invalid_status(self) -> None:
        """Невалидный статус не меняет уже сохранённую задачу."""
        task = await self.service.add_task("Проверить задачу", "@sergey")

        with self.assertRaises(InvalidTaskStatusError):
            await self.service.update_task_status(task.id, "В работе")

        stored = (await self.service.get_all_tasks())[0]
        self.assertEqual(stored.status, "Новая")

    async def test_empty_task_text_is_rejected(self) -> None:
        """Пустые задачи не попадают в хранилище."""
        with self.assertRaises(EmptyTaskTextError):
            await self.service.add_task("   ", "@sergey")
        self.assertEqual(self.repository.tasks, [])

    async def test_oversized_task_text_is_rejected(self) -> None:
        """Текст длиннее лимита Telegram-сообщения отклоняется."""
        with self.assertRaises(TaskTextTooLongError):
            await self.service.add_task("x" * (MAX_TASK_TEXT_LENGTH + 1), "@sergey")

    async def test_csv_contains_header_and_all_tasks(self) -> None:
        """Экспорт включает заголовки, задачи и их количество."""
        await self.service.add_task("Первая задача", "@sergey")
        await self.service.add_task("Вторая задача", "12345")

        export = await self.service.export_tasks_csv()
        csv_text = export.content.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(csv_text), delimiter=";"))

        self.assertEqual(export.task_count, 2)
        self.assertEqual(
            csv_text.splitlines()[0],
            "id;text;user;created_at_utc;category;status",
        )
        self.assertEqual([row[1] for row in rows[1:]], ["Первая задача", "Вторая задача"])
        self.assertEqual(rows[1][4:6], ["Общее", "Новая"])

    async def test_csv_datetime_has_human_readable_format(self) -> None:
        """В CSV время выводится как ДД.ММ.ГГГГ ЧЧ:ММ без микросекунд."""
        task = Task(
            id=1,
            text="Позвонить",
            user="@sergey",
            created_at=datetime(
                2026, 11, 18, 20, 8, 44, 525917, tzinfo=timezone.utc
            ),
        )

        content = self.exporter.export([task]).decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(content), delimiter=";"))

        self.assertEqual(rows[1][3], "18.11.2026 20:08")

    async def test_csv_keeps_semicolon_inside_task_text(self) -> None:
        """Точка с запятой в тексте не разбивает строку на лишние столбцы."""
        await self.service.add_task("Отчёт; срочно", "@sergey")

        export = await self.service.export_tasks_csv()
        rows = list(
            csv.reader(io.StringIO(export.content.decode("utf-8-sig")), delimiter=";")
        )

        self.assertEqual(len(rows[1]), 6)
        self.assertEqual(rows[1][1], "Отчёт; срочно")
