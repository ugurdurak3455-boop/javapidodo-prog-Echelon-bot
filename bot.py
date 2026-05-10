import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from loguru import logger

import database as db
from config import settings
from handlers import admin_router, callbacks_router, commands_router
from tasks import cleanup_loop, notification_loop, parser_loop
from utils.middleware import AutoRegisterMiddleware, RateLimitMiddleware


def _setup_logging():
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format=(
            "<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | <level>{message}</level>"
        ),
    )
    logger.add("storage/logs/bot.log", rotation="10 MB", retention="5 days", compression="zip", level="INFO")

    import logging

    class InterceptHandler(logging.Handler):
        def emit(self, record):
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno
            from types import FrameType
            frame: FrameType | None = sys._getframe(6)
            depth = 6
            while frame and frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back
                depth += 1
            logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)


async def main():
    _setup_logging()

    if not settings.BOT_TOKEN or ":" not in settings.BOT_TOKEN:
        logger.critical("BOT_TOKEN is invalid or missing in .env")
        return

    await db.init_db()
    await db.init_models_from_config()

    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.message.middleware(RateLimitMiddleware(limit=0.5))
    dp.callback_query.middleware(RateLimitMiddleware(limit=0.5))
    dp.update.middleware(AutoRegisterMiddleware())

    dp.include_router(commands_router)
    dp.include_router(callbacks_router)
    dp.include_router(admin_router)

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Главное меню"),
            BotCommand(command="models", description="Выбрать модели"),
            BotCommand(command="city", description="Выбрать города"),
            BotCommand(command="favorites", description="Избранное"),
        ]
    )

    try:
        me = await bot.get_me()
        logger.info(f"Bot started: @{me.username}")

        async with asyncio.TaskGroup() as tg:
            tg.create_task(cleanup_loop())
            tg.create_task(parser_loop(bot))
            tg.create_task(notification_loop(bot))

            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot)

    except* asyncio.CancelledError:
        pass
    except* Exception as eg:
        for exc in eg.exceptions:
            logger.critical(f"Critical task error: {exc}", exc_info=exc)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
