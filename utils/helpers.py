"""
utils/helpers.py — вспомогательные утилиты:
                    clean_input, parse_price_range, декоратор @error_handler
                    для перехвата ошибок в хендлерах.
"""

import asyncio
import html
import logging
from functools import wraps

from aiogram.types import CallbackQuery, Message

import database as db

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "Бот находит выгодные предложения на Avito.\n\n"
    "Команды:\n"
    "/start — главное меню\n"
    "/models — выбор моделей для мониторинга\n"
    "/city — выбор города\n"
    "/status — текущие настройки\n"
    "/favorites — избранные объявления\n"
    "/help — это сообщение\n\n"
    "Уведомления приходят, когда цена ниже медианы на заданный процент."
)


async def get_status_text(user_id: int) -> str:
    """Формирует текст текущего статуса мониторинга для пользователя."""
    user_models, user, cities, savings = await asyncio.gather(
        db.get_user_models(user_id),
        db.get_user(user_id),
        db.get_cities(user_id),
        db.get_user_savings(user_id),
    )

    if not user:
        return "Вы не зарегистрированы. Используйте /start"

    cities_str = ", ".join(cities)
    joined = user.joined_at.strftime("%Y-%m-%d") if user.joined_at else "—"
    savings_str = f"{savings:,}".replace(",", " ")

    if not user_models:
        return (
            f"📍 Города: <b>{cities_str}</b>\n"
            f"📦 Модели: <b>не выбраны</b>\n\n"
            f"🔥 Сэкономлено: <b>{savings_str}₽</b>\n"
            f"📅 Регистрация: <b>{joined}</b>\n\n"
            f"Используйте /models для выбора."
        )

    models_str = "\n".join(
        f"  ├ {html.escape(m.name)} ({m.price_min}–{m.price_max}₽)" for m in user_models
    )
    return (
        f"📍 Города: <b>{cities_str}</b>\n"
        f"📦 Модели ({len(user_models)}):\n{models_str}\n\n"
        f"🔥 Сэкономлено: <b>{savings_str}₽</b>\n"
        f"📅 Регистрация: <b>{joined}</b>"
    )


def error_handler(func):
    @wraps(func)
    async def wrapper(event, *args, **kwargs):
        try:
            return await func(event, *args, **kwargs)
        except Exception as e:
            logger.exception(f"Error in {func.__name__}: {e}")
            msg = "Произошла ошибка. Попробуйте позже."
            if isinstance(event, Message):
                await event.answer(msg)
            elif isinstance(event, CallbackQuery):
                await event.answer(msg, show_alert=True)

    return wrapper
