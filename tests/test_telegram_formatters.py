"""Тесты форматирования сообщений Telegram."""

import unittest
from datetime import datetime, timezone

from core.models import Task
from ui.telegram.formatters import (
    MAX_MESSAGE_LENGTH,
    format_csv_caption,
    format_task_added,
    format_task_done,
    format_task_list,
)


class TelegramFormatterTests(unittest.TestCase):
    """Проверяет список, подтверждение добавления и подпись CSV."""

    def test_empty_list_has_helpful_message(self) -> None:
        """Для пустой базы возвращается сообщение с подсказкой."""
        messages = format_task_list([])

        self.assertEqual(len(messages), 1)
        self.assertIn("Список задач пока пуст", messages[0])
        self.assertIn("/add", messages[0])

    def test_long_list_is_split_without_losing_tasks(self) -> None:
        """Каждая задача попадает в допустимое по длине сообщение."""
        created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        tasks = [
            Task(id=1, text="A" * 2500, user="@alice", created_at=created_at),
            Task(id=2, text="B" * 2500, user="@bob", created_at=created_at),
        ]

        messages = format_task_list(tasks)
        combined = "\n".join(messages)

        self.assertEqual(len(messages), 2)
        self.assertTrue(all(len(message) <= MAX_MESSAGE_LENGTH for message in messages))
        self.assertIn("A" * 2500, combined)
        self.assertIn("B" * 2500, combined)

    def test_task_time_is_shown_in_moscow_time(self) -> None:
        """UTC-время задачи отображается по Москве (UTC+3)."""
        task = Task(
            id=1,
            text="Позвонить клиенту",
            user="@alice",
            created_at=datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc),
        )

        message = format_task_list([task])[0]

        self.assertIn("01.01.2026 03:30 МСК", message)

    def test_task_text_is_escaped_for_html(self) -> None:
        """Пользовательский текст не ломает HTML-разметку Telegram."""
        task = Task(
            id=1,
            text="<b>важно</b> & срочно",
            user="@alice",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        message = format_task_list([task])[0]

        self.assertIn("&lt;b&gt;важно&lt;/b&gt; &amp; срочно", message)
        self.assertNotIn("<b>важно</b>", message)

    def test_list_shows_category_and_status(self) -> None:
        """В списке рядом с задачей видны категория и статус."""
        task = Task(
            id=1,
            text="Сделать кнопку",
            user="@sergey",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            category="Разработка",
            status="Старая",
        )

        message = format_task_list([task])[0]

        self.assertIn("#1", message)
        self.assertIn("[Разработка]", message)
        self.assertIn("Статус: Старая", message)

    def test_added_confirmation_contains_task_details(self) -> None:
        """Подтверждение содержит ID, текст и автора задачи."""
        task = Task(
            id=7,
            text="Купить продукты",
            user="@sergey",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        message = format_task_added(task)

        self.assertIn("✅", message)
        self.assertIn("ID:</b> 7", message)
        self.assertIn("Купить продукты", message)
        self.assertIn("@sergey", message)
        self.assertIn("Категория:</b> Общее", message)
        self.assertIn("Статус:</b> Новая", message)

    def test_done_message_contains_task_number(self) -> None:
        """Сообщение об успехе содержит номер выполненной задачи."""
        message = format_task_done(2)

        self.assertIn("✅", message)
        self.assertIn("#2", message)
        self.assertIn("выполненная", message)

    def test_csv_caption_contains_task_count(self) -> None:
        """Подпись к файлу показывает общее количество задач."""
        self.assertIn("3 шт.", format_csv_caption(3))
