"""Форматирование сообщений Telegram-бота."""

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from html import escape

from core.models import Task


MAX_MESSAGE_LENGTH = 4000

# Текст задачи в сообщении ограничиваем с запасом: после HTML-экранирования
# символы вроде `<` и `&` занимают до пяти символов и могут превысить лимит.
MAX_TASK_TEXT_IN_MESSAGE = 3000

# Москва живёт в UTC+3 круглый год, поэтому фиксированный сдвиг надёжнее
# базы часовых поясов, которой может не быть в Windows.
MOSCOW_TZ = timezone(timedelta(hours=3), name="MSK")

EMPTY_LIST_MESSAGE = (
    "📭 <b>Список задач пока пуст.</b>\n\n"
    "➕ Добавьте первую задачу командой /add"
)


def format_start_greeting() -> str:
    """Возвращает приветствие для `/start` в разметке HTML.

    Угловые скобки в подсказке `/add <текст>` экранируются, иначе Telegram
    попытается разобрать их как HTML-тег и отклонит сообщение.
    """
    text_placeholder = escape("<текст>", quote=False)
    return (
        "👋 <b>Привет!</b> Я бот для командной работы и добавления задач.\n\n"
        "📋 <b>Доступные команды:</b>\n"
        f"➕ /add {text_placeholder} — добавить задачу\n"
        "📌 /list — показать все задачи\n"
        f"✅ /done {escape('<номер>', quote=False)} — отметить задачу выполненной\n"
        "📥 /list_csv — скачать CSV-файл со списком\n\n"
        "🚀 Используй /add, чтобы добавить задачу!"
    )


def format_task_datetime(value: datetime) -> str:
    """Переводит время задачи в московское и форматирует для показа."""
    return value.astimezone(MOSCOW_TZ).strftime("%d.%m.%Y %H:%M МСК")


def format_task_added(task: Task) -> str:
    """Оформляет подтверждение добавления задачи."""
    text = _escape_and_limit(task.text)
    user = escape(task.user, quote=False)
    return (
        "✅ <b>Задача успешно добавлена!</b>\n\n"
        f"🆔 <b>ID:</b> {task.id}\n"
        f"📝 <b>Текст:</b> {text}\n"
        f"👤 <b>Автор:</b> {user}\n"
        f"📂 <b>Категория:</b> {escape(task.category, quote=False)}\n"
        f"🏷 <b>Статус:</b> {escape(task.status, quote=False)}"
    )


def format_task_list(tasks: Sequence[Task]) -> list[str]:
    """Формирует одно или несколько сообщений с задачами.

    Каждая задача оформляется отдельным блоком с эмодзи. Если блоков много,
    сообщения делятся по границе задач, чтобы не разрывать описание.
    """
    if not tasks:
        return [EMPTY_LIST_MESSAGE]

    messages: list[str] = []
    current = "📋 <b>Список задач:</b>"
    for task in tasks:
        block = "\n\n" + _format_task_block(task)
        if len(current) + len(block) > MAX_MESSAGE_LENGTH and current:
            messages.append(current)
            current = "📋 <b>Продолжение списка задач:</b>"
        current += block
    messages.append(current)
    return messages


def format_task_done(task_id: int) -> str:
    """Оформляет сообщение об успешном выполнении задачи."""
    return f"✅ <b>Готово!</b> Задача #{task_id} отмечена как выполненная."


def format_csv_caption(task_count: int) -> str:
    """Возвращает подпись к CSV-файлу с количеством задач."""
    return f"📋 <b>Список задач</b> ({task_count} шт.)"


def format_error(message: str) -> str:
    """Оформляет текст ошибки с предупреждающим эмодзи."""
    return f"⚠️ {escape(message, quote=False)}"


def _format_task_block(task: Task) -> str:
    """Собирает HTML-блок одной задачи для команды `/list`.

    Категория и статус стоят рядом с задачей, чтобы их было видно
    без чтения всей карточки: `#1 [Разработка] Текст — Статус: Новая`.
    """
    text = _escape_and_limit(task.text)
    user = escape(task.user, quote=False)
    category = escape(task.category, quote=False)
    status = escape(task.status, quote=False)
    return (
        f"🆔 <b>#{task.id}</b> 📂 [{category}] {text} — "
        f"🏷 Статус: {status}\n"
        f"👤 {user}\n"
        f"🕒 {format_task_datetime(task.created_at)}"
    )


def _escape_and_limit(value: str) -> str:
    """Экранирует текст для HTML и безопасно сокращает слишком длинный."""
    escaped = escape(value, quote=False)
    if len(escaped) <= MAX_TASK_TEXT_IN_MESSAGE:
        return escaped

    shortened = escaped[: MAX_TASK_TEXT_IN_MESSAGE - 1]
    # Нельзя разрывать HTML-сущность (`&amp;`, `&lt;`) — Telegram её не поймёт.
    last_ampersand = shortened.rfind("&")
    if last_ampersand != -1 and ";" not in shortened[last_ampersand:]:
        shortened = shortened[:last_ampersand]
    return shortened + "…"
