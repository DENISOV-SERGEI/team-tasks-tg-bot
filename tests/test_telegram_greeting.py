"""Тесты приветствия и кнопки Start."""

import unittest

from core.models import TASK_CATEGORIES
from ui.telegram.formatters import format_start_greeting
from ui.telegram.keyboards import (
    START_BUTTON_TEXT,
    category_keyboard,
    main_menu_keyboard,
)


class StartGreetingTests(unittest.TestCase):
    """Проверяет текст приветствия и клавиатуру запуска."""

    def test_greeting_lists_all_commands_in_html(self) -> None:
        """Приветствие содержит команды, эмодзи и экранированную подсказку."""
        greeting = format_start_greeting()

        for command in ("/add", "/list", "/done", "/list_csv"):
            self.assertIn(command, greeting)
        self.assertIn("<b>", greeting)
        self.assertIn("👋", greeting)
        self.assertIn("&lt;текст&gt;", greeting)
        self.assertIn("&lt;номер&gt;", greeting)
        # Сырой тег <текст> сломал бы разметку HTML в Telegram.
        self.assertNotIn("<текст>", greeting)

    def test_keyboard_has_start_button(self) -> None:
        """Постоянная клавиатура содержит кнопку Start."""
        keyboard = main_menu_keyboard()

        self.assertEqual(keyboard.keyboard[0][0].text, START_BUTTON_TEXT)
        self.assertTrue(keyboard.is_persistent)
        self.assertTrue(keyboard.resize_keyboard)

    def test_category_keyboard_has_all_categories(self) -> None:
        """Клавиатура категорий содержит все варианты в нужном порядке."""
        keyboard = category_keyboard()
        button_texts = [
            button.text for row in keyboard.keyboard for button in row
        ]

        self.assertEqual(tuple(button_texts), TASK_CATEGORIES)
        self.assertTrue(keyboard.one_time_keyboard)
