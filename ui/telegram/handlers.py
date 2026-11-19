"""Обработчики Telegram-команд и пошаговое добавление задач."""

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, Message, ReplyKeyboardRemove

from core.errors import TaskRepositoryError, TaskValidationError
from core.models import TASK_CATEGORIES
from core.services import TaskService
from ui.telegram.formatters import (
    format_csv_caption,
    format_error,
    format_start_greeting,
    format_task_added,
    format_task_done,
    format_task_list,
)
from ui.telegram.keyboards import (
    START_BUTTON_TEXT,
    category_keyboard,
    main_menu_keyboard,
)
from ui.telegram.states import AddTaskStates


logger = logging.getLogger(__name__)
STORAGE_UNAVAILABLE_MESSAGE = (
    "⚠️ Хранилище временно недоступно. Попробуйте ещё раз позже."
)


def _log_storage_error(operation: str, error: TaskRepositoryError) -> None:
    """Записывает безопасный контекст сбоя без текста ошибки или данных пользователя."""
    logger.error(
        "Сбой хранилища при операции «%s» (тип: %s).",
        operation,
        type(error).__name__,
    )


def create_task_router(task_service: TaskService) -> Router:
    """Создаёт роутер и связывает команды с бизнес-сервисом."""
    router = Router(name="tasks")

    async def send_greeting(message: Message, state: FSMContext) -> None:
        """Отправляет HTML-приветствие и постоянную кнопку Start."""
        # Сбрасываем незавершённый ввод задачи, чтобы Start всегда начинал заново.
        await state.clear()
        await message.answer(
            format_start_greeting(),
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )

    async def ask_category(message: Message) -> None:
        """Показывает второй шаг — выбор категории из reply-клавиатуры."""
        await message.answer(
            "📂 <b>Шаг 2 из 2.</b> Выберите категорию задачи:",
            parse_mode="HTML",
            reply_markup=category_keyboard(),
        )

    @router.message(CommandStart())
    async def start_handler(message: Message, state: FSMContext) -> None:
        """Приветствует пользователя по команде `/start`."""
        await send_greeting(message, state)

    @router.message(F.text == START_BUTTON_TEXT)
    async def start_button_handler(message: Message, state: FSMContext) -> None:
        """Реагирует на кнопку Start так же, как на команду `/start`."""
        await send_greeting(message, state)

    @router.message(Command("add"))
    async def add_handler(
        message: Message,
        command: CommandObject,
        state: FSMContext,
    ) -> None:
        """Запускает добавление задачи в два шага.

        Если текст передан сразу (`/add Купить хлеб`), пользователю остаётся
        только выбрать категорию. Без текста бот сначала попросит его ввести.
        """
        # Новый вызов /add всегда начинается с чистого состояния,
        # чтобы старые данные не попали в новую задачу.
        await state.clear()

        text = (command.args or "").strip()
        if text:
            await state.update_data(task_text=text)
            await state.set_state(AddTaskStates.waiting_for_category)
            await ask_category(message)
            return

        await state.set_state(AddTaskStates.waiting_for_text)
        await message.answer(
            "✍️ <b>Шаг 1 из 2.</b> Введите текст задачи:\n\n"
            "🚫 /cancel — отменить добавление",
            parse_mode="HTML",
        )

    @router.message(
        Command("cancel"),
        StateFilter(
            AddTaskStates.waiting_for_text,
            AddTaskStates.waiting_for_category,
        ),
    )
    async def cancel_add_handler(message: Message, state: FSMContext) -> None:
        """Отменяет добавление на любом шаге и убирает клавиатуру."""
        await state.clear()
        await message.answer(
            "🚫 Добавление задачи отменено.",
            reply_markup=ReplyKeyboardRemove(),
        )

    @router.message(AddTaskStates.waiting_for_text, F.text, ~F.text.startswith("/"))
    async def add_text_handler(message: Message, state: FSMContext) -> None:
        """Запоминает текст задачи и переводит на шаг выбора категории."""
        # FSMContext хранит данные между сообщениями: пользователь пришлёт
        # категорию отдельным сообщением, а текст нужно не потерять.
        await state.update_data(task_text=message.text)
        await state.set_state(AddTaskStates.waiting_for_category)
        await ask_category(message)

    @router.message(AddTaskStates.waiting_for_text, ~F.text)
    async def non_text_handler(message: Message) -> None:
        """Просит прислать именно текст, если ожидается описание задачи."""
        await message.answer(
            "✍️ Пожалуйста, отправьте текст задачи или используйте /cancel."
        )

    @router.message(AddTaskStates.waiting_for_category, F.text.in_(TASK_CATEGORIES))
    async def category_handler(message: Message, state: FSMContext) -> None:
        """Сохраняет задачу с выбранной категорией."""
        data = await state.get_data()
        text = (data.get("task_text") or "").strip()

        # Защита от редкого случая: состояние есть, а текст потерялся.
        if not text:
            await state.clear()
            await message.answer(
                "⚠️ Не удалось восстановить текст задачи. Начните заново: /add",
                reply_markup=ReplyKeyboardRemove(),
            )
            return

        await save_task(
            message=message,
            text=text,
            category=message.text or "",
            state=state,
            task_service=task_service,
        )

    @router.message(
        AddTaskStates.waiting_for_category,
        F.text,
        ~F.text.startswith("/"),
        ~F.text.in_(TASK_CATEGORIES),
    )
    async def invalid_category_handler(message: Message) -> None:
        """Просит выбрать категорию кнопкой, если ввели произвольный текст."""
        await message.answer(
            "📂 Пожалуйста, выберите категорию с помощью кнопок ниже.",
            reply_markup=category_keyboard(),
        )

    @router.message(AddTaskStates.waiting_for_category, ~F.text)
    async def invalid_category_content_handler(message: Message) -> None:
        """Напоминает про кнопки, если вместо текста прислали файл или фото."""
        await message.answer(
            "📂 Пожалуйста, выберите категорию с помощью кнопок ниже.",
            reply_markup=category_keyboard(),
        )

    @router.message(Command("list"))
    async def list_handler(message: Message) -> None:
        """Отправляет общий список, разбивая его на сообщения."""
        try:
            tasks = await task_service.get_all_tasks()
        except TaskRepositoryError as error:
            _log_storage_error("получение списка", error)
            await message.answer(STORAGE_UNAVAILABLE_MESSAGE)
            return

        for chunk in format_task_list(tasks):
            await message.answer(chunk, parse_mode="HTML")

    @router.message(Command("list_csv"))
    async def list_csv_handler(message: Message) -> None:
        """Формирует и отправляет CSV со всеми задачами."""
        try:
            export = await task_service.export_tasks_csv()
        except TaskRepositoryError as error:
            _log_storage_error("экспорт списка", error)
            await message.answer(STORAGE_UNAVAILABLE_MESSAGE)
            return

        document = BufferedInputFile(export.content, filename="tasks.csv")
        await message.answer_document(
            document,
            caption=format_csv_caption(export.task_count),
            parse_mode="HTML",
        )

    @router.message(Command("done"))
    async def done_handler(message: Message, command: CommandObject) -> None:
        """Отмечает задачу выполненной по номеру: `/done 2`."""
        raw_id = (command.args or "").strip()

        # Номер не указан — подсказываем правильный формат команды.
        if not raw_id:
            await message.answer(
                "⚠️ Укажите номер задачи. Например: <code>/done 2</code>",
                parse_mode="HTML",
            )
            return

        try:
            task_id = int(raw_id)
        except ValueError:
            # Пользователь мог отправить `/done два` или `/done 2 3`.
            await message.answer(
                "⚠️ Номер задачи должен быть целым числом. "
                "Например: <code>/done 2</code>",
                parse_mode="HTML",
            )
            return

        # ID в SQLite начинаются с 1, поэтому 0 и отрицательные числа
        # заведомо не существуют — не делаем лишний запрос в базу.
        if task_id <= 0:
            await message.answer(
                "⚠️ Номер задачи должен быть положительным числом. "
                "Например: <code>/done 2</code>",
                parse_mode="HTML",
            )
            return

        try:
            updated = await task_service.mark_task_done(task_id)
        except TaskRepositoryError as error:
            _log_storage_error("смена статуса", error)
            await message.answer(STORAGE_UNAVAILABLE_MESSAGE)
            return

        if not updated:
            await message.answer(
                f"🔍 Задача с номером {task_id} не найдена. "
                "Проверьте номер в /list.",
                parse_mode="HTML",
            )
            return

        await message.answer(format_task_done(task_id), parse_mode="HTML")

    return router


async def save_task(
    message: Message,
    text: str,
    category: str,
    state: FSMContext,
    task_service: TaskService,
) -> None:
    """Сохраняет задачу с категорией, убирает клавиатуру и сообщает об успехе."""
    if message.from_user is None:
        await message.answer("⚠️ Не удалось определить автора задачи.")
        return

    user = (
        f"@{message.from_user.username}"
        if message.from_user.username
        else str(message.from_user.id)
    )
    try:
        task = await task_service.add_task(
            text=text,
            user=user,
            category=category,
        )
    except TaskValidationError as error:
        await state.clear()
        await message.answer(
            format_error(str(error)),
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove(),
        )
        return
    except TaskRepositoryError as error:
        _log_storage_error("сохранение задачи", error)
        await state.clear()
        await message.answer(
            STORAGE_UNAVAILABLE_MESSAGE,
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await state.clear()
    await message.answer(
        format_task_added(task),
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
