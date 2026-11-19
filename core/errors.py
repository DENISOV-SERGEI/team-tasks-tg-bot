"""Ошибки приложения задач."""


class TaskValidationError(ValueError):
    """Базовая ошибка проверки задачи."""


class EmptyTaskTextError(TaskValidationError):
    """Возникает, когда текст задачи пустой."""


class TaskTextTooLongError(TaskValidationError):
    """Возникает, когда текст превышает допустимую длину."""


class InvalidTaskStatusError(TaskValidationError):
    """Возникает, когда статус задачи не входит в допустимый набор."""


class TaskRepositoryError(RuntimeError):
    """Возникает, когда хранилище не может выполнить операцию с задачами."""
