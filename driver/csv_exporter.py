"""Экспорт задач в CSV для передачи через Telegram."""

import csv
import io
from collections.abc import Sequence

from core.models import Task


_FORMULA_PREFIXES = ("=", "+", "-", "@")


class CsvTaskExporter:
    """Создаёт CSV-документ в памяти без временных файлов."""

    def export(self, tasks: Sequence[Task]) -> bytes:
        """Возвращает CSV в UTF-8 с BOM для удобного открытия в Excel."""
        text_buffer = io.StringIO(newline="")
        # Точка с запятой — стандартный разделитель для Excel в русской локали.
        writer = csv.writer(text_buffer, delimiter=";")
        writer.writerow(
            (
                "id",
                "text",
                "user",
                "created_at_utc",
                "category",
                "status",
            )
        )
        for task in tasks:
            writer.writerow(
                (
                    task.id if task.id is not None else "",
                    _sanitize_cell(task.text),
                    _sanitize_cell(task.user),
                    # Excel удобнее читать привычный формат без микросекунд.
                    task.created_at.strftime("%d.%m.%Y %H:%M"),
                    _sanitize_cell(task.category),
                    _sanitize_cell(task.status),
                )
            )
        return text_buffer.getvalue().encode("utf-8-sig")


def _sanitize_cell(value: str) -> str:
    """Добавляет апостроф перед потенциальной формулой, сохраняя исходную строку."""
    if value.lstrip().startswith(_FORMULA_PREFIXES):
        return f"'{value}"
    return value
