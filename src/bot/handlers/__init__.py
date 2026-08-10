from .callbacks import register_callback_handlers
from .commands import register_command_handlers


def register_handlers(app) -> None:
    register_command_handlers(app)
    register_callback_handlers(app)
