"""Проверки ответов Telegram-хендлеров при сбое хранилища."""

import unittest
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import SendDocument, SendMessage
from aiogram.types import Chat, Message, ReplyKeyboardRemove, Update, User

from core.errors import TaskRepositoryError
from core.models import Task
from core.services import TaskService
from driver.csv_exporter import CsvTaskExporter
from ui.telegram.handlers import STORAGE_UNAVAILABLE_MESSAGE, create_task_router
from ui.telegram.states import AddTaskStates


_CHAT_ID = 101
_USER_ID = 101


class RecordingBot(Bot):
    """Записывает запросы Telegram API без обращения к сети."""

    def __init__(self) -> None:
        super().__init__(token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
        self.methods: list[object] = []

    async def __call__(self, method: object, request_timeout: int | None = None) -> None:
        self.methods.append(method)


class FailingTaskRepository:
    """Имитирует недоступное хранилище через контракт репозитория."""

    async def add_task(self, task: Task) -> Task:
        raise TaskRepositoryError("internal database detail")

    async def get_all(self) -> list[Task]:
        raise TaskRepositoryError("internal database detail")

    async def update_status(self, task_id: int, status: str) -> bool:
        raise TaskRepositoryError("internal database detail")


def _make_update(update_id: int, text: str) -> Update:
    """Создаёт приватное текстовое сообщение для подачи в aiogram Dispatcher."""
    return Update(
        update_id=update_id,
        message=Message(
            message_id=update_id,
            date=datetime.now(timezone.utc),
            chat=Chat(id=_CHAT_ID, type="private"),
            from_user=User(id=_USER_ID, is_bot=False, first_name="Test"),
            text=text,
        ),
    )


class TelegramStorageErrorTests(unittest.IsolatedAsyncioTestCase):
    """Проверяет нейтральные ответы и отсутствие ложного успеха."""

    async def asyncSetUp(self) -> None:
        self.bot = RecordingBot()
        self.storage = MemoryStorage()
        self.dispatcher = Dispatcher(storage=self.storage)
        service = TaskService(FailingTaskRepository(), CsvTaskExporter())
        self.dispatcher.include_router(create_task_router(service))

    async def asyncTearDown(self) -> None:
        await self.storage.close()
        await self.bot.session.close()

    def _sent_texts(self) -> list[str]:
        """Возвращает тексты запросов SendMessage."""
        return [
            method.text
            for method in self.bot.methods
            if isinstance(method, SendMessage)
        ]

    async def _assert_storage_failure_logged(self, update: Update) -> None:
        with self.assertLogs("ui.telegram.handlers", level="ERROR") as captured:
            await self.dispatcher.feed_update(self.bot, update)

        self.assertIn("TaskRepositoryError", "\n".join(captured.output))
        self.assertNotIn("internal database detail", "\n".join(captured.output))
        self.assertIn(STORAGE_UNAVAILABLE_MESSAGE, self._sent_texts())

    async def test_add_failure_clears_fsm_and_does_not_confirm_success(self) -> None:
        key = StorageKey(
            bot_id=self.bot.id,
            chat_id=_CHAT_ID,
            user_id=_USER_ID,
        )
        await self.storage.set_state(
            key,
            AddTaskStates.waiting_for_category.state,
        )
        await self.storage.set_data(key, {"task_text": "Prepare report"})

        await self._assert_storage_failure_logged(_make_update(1, "Разработка"))

        self.assertIsNone(await self.storage.get_state(key))
        self.assertNotIn("добавлена", " ".join(self._sent_texts()).lower())
        send_messages = [
            method
            for method in self.bot.methods
            if isinstance(method, SendMessage)
        ]
        self.assertIsInstance(
            send_messages[-1].reply_markup,
            ReplyKeyboardRemove,
        )

    async def test_list_failure_sends_storage_unavailable_message(self) -> None:
        await self._assert_storage_failure_logged(_make_update(2, "/list"))

        self.assertEqual(self._sent_texts(), [STORAGE_UNAVAILABLE_MESSAGE])

    async def test_done_failure_does_not_confirm_status_change(self) -> None:
        await self._assert_storage_failure_logged(_make_update(3, "/done 1"))

        self.assertNotIn("выполнена", " ".join(self._sent_texts()).lower())

    async def test_csv_failure_does_not_send_document(self) -> None:
        await self._assert_storage_failure_logged(_make_update(4, "/list_csv"))

        self.assertFalse(
            any(isinstance(method, SendDocument) for method in self.bot.methods)
        )


if __name__ == "__main__":
    unittest.main()
