"""Тесты безопасности экспорта задач в CSV."""

import csv
import io
import unittest
from datetime import datetime, timezone

from core.models import Task
from driver.csv_exporter import CsvTaskExporter


class CsvTaskExporterSecurityTests(unittest.TestCase):
    """Проверяет нейтрализацию формул в экспортируемом CSV."""

    def test_formula_prefixes_are_neutralized_without_mutating_tasks(self) -> None:
        """Все строковые поля защищаются, а исходные задачи не меняются."""
        source_texts = ("=1+1", "+SUM(1,1)", "-1+2", "@SUM(1,1)")
        tasks = [
            Task(
                id=index,
                text=text,
                user=text,
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                category=text,
                status="Новая",
            )
            for index, text in enumerate(source_texts, start=1)
        ]

        content = CsvTaskExporter().export(tasks).decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(content), delimiter=";"))
        expected_values = [f"'{text}" for text in source_texts]

        for column in (1, 2, 4):
            self.assertEqual(
                [row[column] for row in rows[1:]],
                expected_values,
            )
        self.assertEqual(
            [
                (task.text, task.user, task.category, task.status)
                for task in tasks
            ],
            [(text, text, text, "Новая") for text in source_texts],
        )


if __name__ == "__main__":
    unittest.main()
