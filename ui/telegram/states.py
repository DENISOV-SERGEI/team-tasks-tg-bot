"""Состояния диалога Telegram-бота."""

from aiogram.fsm.state import State, StatesGroup


class AddTaskStates(StatesGroup):
    """Состояния для пошагового добавления задачи."""

    waiting_for_text = State()
    waiting_for_category = State()
