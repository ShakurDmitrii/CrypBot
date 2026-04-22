from aiogram import Router

from src.bot.handlers.operator import router as operator_router
from src.bot.handlers.user import router as user_router


def build_router() -> Router:
    router = Router()
    router.include_router(operator_router)
    router.include_router(user_router)
    return router
