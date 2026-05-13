import asyncio
import sys
from loguru import logger
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import database as db
from config import settings
from tasks import parser_loop


def _setup_logging():
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format=(
            "<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | <level>{message}</level>"
        ),
    )
    logger.add("storage/logs/parser.log", rotation="10 MB", retention="5 days", compression="zip", level="INFO")


async def main():
    _setup_logging()
    logger.info("Starting parser service...")

    await db.init_db()
    await db.init_models_from_config()

    # Initialize bot for sending block warnings if credentials are valid
    bot = None
    if settings.BOT_TOKEN and ":" in settings.BOT_TOKEN:
        bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        logger.info("Bot initialized for admin alerts.")
    else:
        logger.warning("BOT_TOKEN is missing or invalid. Admin alerts will be disabled.")

    try:
        await parser_loop(bot)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Parser service stopped by user request.")
    except Exception as e:
        logger.exception(f"Parser service crashed: {e}")
    finally:
        if bot:
            await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
