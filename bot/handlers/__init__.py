from aiogram import Dispatcher

from bot.handlers.admin import router as admin_router
from bot.handlers.user import router as user_router


def register_routers(dispatcher: Dispatcher) -> None:
    dispatcher.include_router(admin_router)
    dispatcher.include_router(user_router)
