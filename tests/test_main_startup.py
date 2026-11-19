"""Тесты устойчивого запуска: ожидание Telegram и настройка меню.

Проверяется именно то, из-за чего раньше бот завершался при старте:
недоступная сеть не должна ронять процесс, а сбой настройки меню —
не должен мешать polling.
"""

import asyncio
import unittest
from unittest.mock import patch

from aiogram.exceptions import TelegramAPIError, TelegramNetworkError
from aiogram.methods import SendMessage

import main


def _network_error(description: str = "нет сети") -> TelegramNetworkError:
    """Создаёт сетевую ошибку так, как её формирует aiogram."""
    return TelegramNetworkError(SendMessage(chat_id=1, text="ping"), description)


def _api_error() -> TelegramAPIError:
    """Создаёт ошибку Telegram API для проверки вспомогательных вызовов."""
    return TelegramAPIError(SendMessage(chat_id=1, text="ping"), "сбой API")


class FlakyBot:
    """Падает заданное число раз, затем успешно отвечает на get_me."""

    def __init__(
        self,
        failures: int,
        error_description: str = "нет сети",
    ) -> None:
        self.failures = failures
        self.error_description = error_description
        self.calls = 0

    async def get_me(self, request_timeout: int | None = None) -> object:
        self.calls += 1
        if self.failures > 0:
            self.failures -= 1
            raise _network_error(self.error_description)
        return object()


class MenuBot:
    """Запоминает вызовы настройки меню и умеет имитировать сбой."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.commands = []

    async def set_chat_menu_button(self, **kwargs: object) -> bool:
        if self.fail:
            raise _api_error()
        return True

    async def set_my_commands(self, commands: list[object]) -> bool:
        if self.fail:
            raise _api_error()
        self.commands = list(commands)
        return True


class StartupResilienceTests(unittest.TestCase):
    """Проверяет, что запуск переживает недоступную сеть."""

    def test_wait_for_telegram_retries_until_success(self) -> None:
        """Бот повторяет попытки и не завершается при сетевой ошибке."""
        bot = FlakyBot(failures=2)

        # В тестах пауза не нужна: ждать 10 секунд бессмысленно.
        with patch.object(main, "TELEGRAM_RETRY_DELAY_SECONDS", 0):
            asyncio.run(main.wait_for_telegram(bot))  # type: ignore[arg-type]

        self.assertEqual(bot.calls, 3)

    def test_wait_for_telegram_does_not_log_proxy_credentials(self) -> None:
        """Сетевой лог не раскрывает URL прокси с учётными данными."""
        proxy_url = "http://proxy_user:proxy_password@proxy.example:8080"
        bot = FlakyBot(
            failures=1,
            error_description=f"connection failed through {proxy_url}",
        )

        with (
            patch.object(main, "TELEGRAM_RETRY_DELAY_SECONDS", 0),
            self.assertLogs(level="WARNING") as captured,
        ):
            asyncio.run(main.wait_for_telegram(bot))  # type: ignore[arg-type]

        logged_output = "\n".join(captured.output)
        self.assertIn("TelegramNetworkError", logged_output)
        self.assertIn("Повтор через", logged_output)
        self.assertNotIn(proxy_url, logged_output)
        self.assertNotIn("proxy_password", logged_output)

    def test_menu_failure_does_not_stop_startup(self) -> None:
        """Сбой настройки меню только пишется в лог, но не прерывает запуск."""
        with self.assertLogs(level="WARNING") as captured:
            asyncio.run(main.configure_bot_menu(MenuBot(fail=True)))  # type: ignore[arg-type]

        self.assertTrue(any("меню" in line for line in captured.output))

    def test_menu_registers_all_bot_commands(self) -> None:
        """В меню попадают все команды бота, включая /done."""
        bot = MenuBot()

        asyncio.run(main.configure_bot_menu(bot))  # type: ignore[arg-type]

        names = [command.command for command in bot.commands]
        self.assertEqual(
            names,
            ["start", "add", "list", "done", "list_csv"],
        )


if __name__ == "__main__":
    unittest.main()
