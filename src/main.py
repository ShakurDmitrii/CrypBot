import asyncio
import logging
import socket
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError

from src.bot.router import build_router
from src.config import get_settings
from src.db.init_db import create_tables
from src.db.session import engine


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()

    await create_tables(engine)

    # Force IPv4 on this host to avoid intermittent WinError 121 with aiohttp happy-eyeballs.
    session = AiohttpSession(proxy=settings.bot_proxy or None)
    session._connector_init["family"] = socket.AF_INET

    bot = Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher()
    dp.include_router(build_router())

    while True:
        try:
            await dp.start_polling(bot)
            break
        except TelegramNetworkError as exc:
            logging.warning("Telegram network error: %s. Retry in 5s...", exc)
            await asyncio.sleep(5)
        except Exception as exc:
            logging.exception(
                "Unexpected polling error (%s): %s. Retry in 5s...",
                type(exc).__name__,
                exc,
            )
            await asyncio.sleep(5)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
