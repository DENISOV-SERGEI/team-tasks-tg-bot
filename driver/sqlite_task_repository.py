"""Асинхронный SQLite-репозиторий задач."""

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

import aiosqlite

from core.errors import TaskRepositoryError
from core.models import (
    DEFAULT_STATUS,
    OLD_STATUS,
    Task,
    normalize_task_text,
    validate_task_status,
)


class SQLiteTaskRepository:
    """Реализует хранение задач в локальной базе SQLite."""

    def __init__(self, database_path: Path) -> None:
        """Сохраняет путь к базе; соединения открываются только при запросах."""
        self._database_path = database_path

    async def initialize(self) -> None:
        """Создаёт каталог, таблицу и добавляет новые колонки в старую БД.

        `CREATE TABLE IF NOT EXISTS` не изменяет уже существующую таблицу,
        поэтому для баз, созданных прошлыми версиями бота, дополнительно
        выполняется безопасная миграция через `ALTER TABLE`.
        """
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._database_path) as connection:
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    "user" TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'Общее',
                    status TEXT NOT NULL DEFAULT 'Новая'
                )
                """
            )

            # Проверяем, какие колонки уже есть: так миграция не выполнится
            # повторно и не завершится ошибкой "duplicate column name".
            existing_columns = await self._column_names(connection)
            if "category" not in existing_columns:
                await connection.execute(
                    """
                    ALTER TABLE tasks
                    ADD COLUMN category TEXT NOT NULL DEFAULT 'Общее'
                    """
                )
            if "status" not in existing_columns:
                await connection.execute(
                    """
                    ALTER TABLE tasks
                    ADD COLUMN status TEXT NOT NULL DEFAULT 'Новая'
                    """
                )

            await connection.commit()

    async def add_task(self, task: Task) -> Task:
        """Атомарно сохраняет задачу со статусом «Новая» или «Старая»."""
        normalized_text = normalize_task_text(task.text)
        try:
            async with aiosqlite.connect(self._database_path) as connection:
                await connection.execute("BEGIN IMMEDIATE")
                try:
                    cursor = await connection.execute("SELECT text FROM tasks")
                    existing_texts = await cursor.fetchall()
                    await cursor.close()

                    is_duplicate = any(
                        normalize_task_text(row[0]) == normalized_text
                        for row in existing_texts
                    )
                    status = OLD_STATUS if is_duplicate else DEFAULT_STATUS
                    cursor = await connection.execute(
                        """
                        INSERT INTO tasks (text, "user", created_at, category, status)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            task.text,
                            task.user,
                            task.created_at.isoformat(),
                            task.category,
                            status,
                        ),
                    )
                    task_id = cursor.lastrowid
                    await cursor.close()
                    if task_id is None:
                        raise TaskRepositoryError(
                            "SQLite не вернула ID сохранённой задачи."
                        )
                    await connection.commit()
                except BaseException:
                    await connection.rollback()
                    raise
        except (sqlite3.Error, OSError) as error:
            raise TaskRepositoryError("Не удалось сохранить задачу.") from error

        return replace(task, id=task_id, status=status)

    async def get_all(self) -> list[Task]:
        """Возвращает задачи от старых к новым."""
        try:
            async with aiosqlite.connect(self._database_path) as connection:
                connection.row_factory = aiosqlite.Row
                cursor = await connection.execute(
                    """
                    SELECT id, text, "user", created_at, category, status
                    FROM tasks
                    ORDER BY created_at, id
                    """
                )
                rows = await cursor.fetchall()
                await cursor.close()
        except (sqlite3.Error, OSError) as error:
            raise TaskRepositoryError("Не удалось получить список задач.") from error

        return [
            Task(
                id=row["id"],
                text=row["text"],
                user=row["user"],
                created_at=self._parse_datetime(row["created_at"]),
                category=row["category"],
                status=row["status"],
            )
            for row in rows
        ]

    async def update_status(self, task_id: int, status: str) -> bool:
        """Меняет статус задачи по её ID.

        Возвращает `True`, если задача найдена и обновлена, и `False`,
        если задачи с таким ID нет. Пустой статус запрещён.
        """
        clean_status = validate_task_status(status)

        try:
            async with aiosqlite.connect(self._database_path) as connection:
                cursor = await connection.execute(
                    "UPDATE tasks SET status = ? WHERE id = ?",
                    (clean_status, task_id),
                )
                await connection.commit()

                # rowcount > 0 значит, что строка с таким ID действительно была.
                updated = cursor.rowcount > 0
                await cursor.close()
        except (sqlite3.Error, OSError) as error:
            raise TaskRepositoryError("Не удалось изменить статус задачи.") from error

        return updated

    @staticmethod
    async def _column_names(connection: aiosqlite.Connection) -> set[str]:
        """Возвращает имена колонок таблицы tasks для проверки миграций."""
        cursor = await connection.execute("PRAGMA table_info(tasks)")
        rows = await cursor.fetchall()
        await cursor.close()

        # В каждой строке PRAGMA имя колонки находится на позиции 1.
        return {row[1] for row in rows}

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        """Читает ISO-время и поддерживает старые записи без часового пояса."""
        created_at = datetime.fromisoformat(value)
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return created_at.astimezone(timezone.utc)
