"""Тесты SQLite-репозитория на временной базе."""

import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from core.errors import InvalidTaskStatusError
from core.models import DEFAULT_STATUS, DONE_STATUS, OLD_STATUS, Task
from core.services import TaskService
from driver.csv_exporter import CsvTaskExporter
from driver.sqlite_task_repository import SQLiteTaskRepository


class SQLiteTaskRepositoryTests(unittest.IsolatedAsyncioTestCase):
    """Проверяет сохранение и чтение задач в SQLite."""

    async def asyncSetUp(self) -> None:
        """Создаёт временную базу, не затрагивая рабочие данные."""
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_directory.name) / "tasks.db"
        self.repository = SQLiteTaskRepository(self.database_path)
        await self.repository.initialize()

    async def asyncTearDown(self) -> None:
        """Удаляет временные тестовые данные."""
        self.temp_directory.cleanup()

    async def test_tasks_are_persisted_in_insertion_order(self) -> None:
        """Задачи сохраняются и читаются в ожидаемом порядке."""
        first = Task(
            id=None,
            text="Первая задача",
            user="@alice",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        second = Task(
            id=None,
            text="Вторая задача",
            user="@bob",
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )

        saved_first = await self.repository.add_task(first)
        saved_second = await self.repository.add_task(second)
        tasks = await self.repository.get_all()

        self.assertEqual(saved_first.id, 1)
        self.assertEqual(saved_second.id, 2)
        self.assertEqual([task.text for task in tasks], ["Первая задача", "Вторая задача"])
        self.assertEqual([task.user for task in tasks], ["@alice", "@bob"])
        self.assertEqual([task.category for task in tasks], ["Общее", "Общее"])
        self.assertEqual([task.status for task in tasks], ["Новая", "Новая"])

    async def test_category_is_saved_and_new_status_is_assigned(self) -> None:
        """Репозиторий сохраняет категорию и назначает статус новой задачи."""
        task = Task(
            id=None,
            text="Сверстать экран",
            user="@designer",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            category="Дизайн",
        )

        saved = await self.repository.add_task(task)
        stored = (await self.repository.get_all())[0]

        self.assertEqual(saved.category, "Дизайн")
        self.assertEqual(stored.category, "Дизайн")
        self.assertEqual(stored.status, DEFAULT_STATUS)

    async def test_duplicate_task_in_database_is_marked_old(self) -> None:
        """Сервис распознаёт повтор, уже сохранённый в SQLite."""
        service = TaskService(self.repository, CsvTaskExporter())

        await service.add_task("Подготовить отчёт", "@alice")
        duplicate = await service.add_task(" подготовить   ОТЧЁТ ", "@bob")
        stored_tasks = await self.repository.get_all()

        self.assertEqual(duplicate.status, "Старая")
        self.assertEqual(
            [task.status for task in stored_tasks],
            ["Новая", "Старая"],
        )

    async def test_update_status_changes_only_existing_task(self) -> None:
        """Смена статуса работает по ID и сообщает, найдена ли задача."""
        task = Task(
            id=None,
            text="Проверить отчёт",
            user="@tester",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        saved = await self.repository.add_task(task)

        updated = await self.repository.update_status(saved.id, DONE_STATUS)
        missing = await self.repository.update_status(9999, DONE_STATUS)
        stored = (await self.repository.get_all())[0]

        self.assertTrue(updated)
        self.assertFalse(missing)
        self.assertEqual(stored.status, DONE_STATUS)

    async def test_update_status_rejects_invalid_values(self) -> None:
        """Репозиторий не записывает пустые и неизвестные статусы."""
        task = Task(
            id=None,
            text="Проверить отчёт",
            user="@tester",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        saved = await self.repository.add_task(task)

        for status in ("", "В работе"):
            with self.subTest(status=status):
                with self.assertRaises(InvalidTaskStatusError):
                    await self.repository.update_status(saved.id, status)

        stored = (await self.repository.get_all())[0]
        self.assertEqual(stored.status, "Новая")

    async def test_initialize_is_safe_to_run_more_than_once(self) -> None:
        """Повторная инициализация не удаляет существующие задачи."""
        task = Task(
            id=None,
            text="Сохранить данные",
            user="42",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        await self.repository.add_task(task)

        await self.repository.initialize()

        self.assertEqual(len(await self.repository.get_all()), 1)

    async def test_initialize_migrates_legacy_schema_without_losing_tasks(self) -> None:
        """Миграция добавляет новые поля и сохраняет старые записи."""
        legacy_database_path = Path(self.temp_directory.name) / "legacy_tasks.db"
        legacy_tasks = [
            (1, "Первая задача", "@alice", "2026-01-01T00:00:00+00:00"),
            (2, "Вторая задача", "@bob", "2026-01-02T00:00:00+00:00"),
        ]
        async with aiosqlite.connect(legacy_database_path) as connection:
            await connection.execute(
                """
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY,
                    text TEXT NOT NULL,
                    "user" TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            await connection.executemany(
                """
                INSERT INTO tasks (id, text, "user", created_at)
                VALUES (?, ?, ?, ?)
                """,
                legacy_tasks,
            )
            await connection.commit()

        legacy_repository = SQLiteTaskRepository(legacy_database_path)
        await legacy_repository.initialize()

        async with aiosqlite.connect(legacy_database_path) as connection:
            cursor = await connection.execute("PRAGMA table_info(tasks)")
            columns = {row[1] for row in await cursor.fetchall()}
            await cursor.close()

            cursor = await connection.execute(
                """
                SELECT id, text, "user", created_at, category, status
                FROM tasks
                ORDER BY id
                """
            )
            migrated_tasks = await cursor.fetchall()
            await cursor.close()

        self.assertIn("category", columns)
        self.assertIn("status", columns)
        self.assertEqual(
            migrated_tasks,
            [
                (*legacy_tasks[0], "Общее", "Новая"),
                (*legacy_tasks[1], "Общее", "Новая"),
            ],
        )

        duplicate = await legacy_repository.add_task(
            Task(
                id=None,
                text=" первая   ЗАДАЧА ",
                user="@charlie",
                created_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
            )
        )
        self.assertEqual(duplicate.status, OLD_STATUS)

    async def test_concurrent_duplicate_tasks_are_marked_atomically(self) -> None:
        """Параллельное добавление дублей получает один новый и один старый статус."""
        first = Task(
            id=None,
            text="Подготовить отчёт",
            user="@alice",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        second = Task(
            id=None,
            text=" подготовить   ОТЧЁТ ",
            user="@bob",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        added_tasks = await asyncio.gather(
            self.repository.add_task(first),
            self.repository.add_task(second),
        )

        self.assertCountEqual(
            [task.status for task in added_tasks],
            [DEFAULT_STATUS, OLD_STATUS],
        )
        self.assertEqual(
            [task.status for task in await self.repository.get_all()].count(
                DEFAULT_STATUS
            ),
            1,
        )
        self.assertEqual(
            (first.status, second.status),
            (DEFAULT_STATUS, DEFAULT_STATUS),
        )
