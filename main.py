"""Точка входа: настройка и запуск Telegram-бота."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramAPIError, TelegramNetworkError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonCommands

from config import Settings
from core.services import TaskService
from driver.csv_exporter import CsvTaskExporter
from driver.sqlite_task_repository import SQLiteTaskRepository
from ui.telegram.handlers import create_task_router


# Пауза между попытками подключиться к Telegram при старте.
TELEGRAM_RETRY_DELAY_SECONDS = 10


async def configure_bot_menu(bot: Bot) -> None:
    """Настраивает меню команд, не прерывая запуск при сбое сети.

    Настройка меню — вспомогательная операция. Если Telegram временно
    недоступен, бот должен продолжить работу, а не завершиться с ошибкой.
    """
    try:
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Приветствие и список команд"),
                BotCommand(command="add", description="Добавить задачу"),
                BotCommand(command="list", description="Показать все задачи"),
                BotCommand(command="done", description="Отметить задачу выполненной"),
                BotCommand(command="list_csv", description="Скачать CSV-файл"),
            ]
        )
    except TelegramAPIError as error:
        logging.warning("Не удалось настроить меню команд: %s", error)


async def wait_for_telegram(bot: Bot) -> None:
    """Ждёт доступности Telegram, чтобы бот пережил старт без сети.

    Без этого первая же сетевая ошибка завершала процесс, и все команды
    в меню переставали отвечать до ручного перезапуска.
    """
    while True:
        try:
            # Короткий таймаут, чтобы при отсутствии сети не ждать минуту.
            await bot.get_me(request_timeout=10)
            return
        except TelegramNetworkError as error:
            logging.warning(
                "Telegram недоступен (%s). Повтор через %s секунд.",
                type(error).__name__,
                TELEGRAM_RETRY_DELAY_SECONDS,
            )
            await asyncio.sleep(TELEGRAM_RETRY_DELAY_SECONDS)


async def main() -> None:
    """Создаёт зависимости, подготавливает SQLite и запускает polling."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = Settings.from_env()
    repository = SQLiteTaskRepository(settings.database_path)
    await repository.initialize()

    task_service = TaskService(repository, CsvTaskExporter())
    # Если в .env задан прокси, все запросы к Telegram пойдут через него.
    session = (
        AiohttpSession(proxy=settings.proxy_url) if settings.proxy_url else None
    )
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=None),
        session=session,
    )

    try:
        # Сначала дожидаемся связи: без Telegram polling всё равно не запустится.
        await wait_for_telegram(bot)

        # Затем обновляем меню. Ошибка здесь больше не роняет бота.
        await configure_bot_menu(bot)

        dispatcher = Dispatcher(storage=MemoryStorage())
        dispatcher.include_router(create_task_router(task_service))
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
