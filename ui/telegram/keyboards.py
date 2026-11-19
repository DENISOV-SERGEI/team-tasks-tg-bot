"""Клавиатуры Telegram-бота."""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from core.models import TASK_CATEGORIES


START_BUTTON_TEXT = "Start"


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Создаёт постоянную клавиатуру с кнопкой запуска.

    Кнопка отправляет обычный текст `Start`, который обработчик распознаёт
    как команду `/start`. Это заменяет старую клавиатуру из предыдущих
    версий бота (например, с кнопкой «Оформить заказ»).
    """
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=START_BUTTON_TEXT)]],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Введите команду или нажмите Start",
    )


def category_keyboard() -> ReplyKeyboardMarkup:
    """Создаёт клавиатуру выбора категории задачи.

    Кнопки расположены по две в ряд, чтобы на телефоне они читались
    как аккуратная сетка, а не длинная лента.
    """
    buttons = [KeyboardButton(text=category) for category in TASK_CATEGORIES]
    rows = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]

    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        # После выбора категории Telegram сам спрячет эту клавиатуру.
        one_time_keyboard=True,
        input_field_placeholder="Выберите категорию",
    )
