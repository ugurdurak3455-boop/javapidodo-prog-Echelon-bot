"""
handlers/commands.py — пользовательские команды:
                        /start, /models, /city, /status, /favorites, /help
"""

import asyncio
import logging

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

import database as db
from config import settings
from utils.helpers import HELP_TEXT, error_handler, get_status_text
from utils.keyboards import FavoriteCB, get_city_keyboard, get_models_keyboard, get_main_reply_keyboard

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
@error_handler
async def cmd_start(message: Message) -> None:
    user_models = await db.get_user_models(message.from_user.id)
    menu_kb = get_main_reply_keyboard()
    if user_models:
        names = ", ".join(m.name for m in user_models)
        await message.answer(
            f"С возвращением! Вы отслеживаете: <b>{names}</b>",
            reply_markup=menu_kb,
        )
    else:
        await message.answer(
            "Привет! Выбери модели для мониторинга выгодных предложений на Avito.",
            reply_markup=menu_kb,
        )

@router.message(F.text == "📋 Мои фильтры")
@error_handler
async def btn_filters(message: Message) -> None:
    await cmd_status(message)

@router.message(F.text == "⭐ Избранное")
@error_handler
async def btn_favorites(message: Message) -> None:
    await cmd_favorites(message)

@router.message(F.text == "🏢 Города")
@error_handler
async def btn_cities(message: Message) -> None:
    await cmd_city(message)

@router.message(F.text == "📱 Модели")
@error_handler
async def btn_models(message: Message) -> None:
    await cmd_models(message)

@router.message(F.text == "⚙️ Настройки")
@error_handler
async def btn_settings(message: Message) -> None:
    from utils.keyboards import get_settings_keyboard
    user = await db.get_user(message.from_user.id)
    if not user:
        return
    kb = get_settings_keyboard(user.min_discount, user.dnd_enabled)
    await message.answer("⚙️ <b>Персональные настройки</b>\n\nЗдесь вы можете настроить порог выгоды для уведомлений и включить тихие часы.", reply_markup=kb)


@router.message(Command("help"))
@error_handler
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("status"))
@error_handler
async def cmd_status(message: Message) -> None:
    await message.answer(await get_status_text(message.from_user.id))


@router.message(Command("models"))
@error_handler
async def cmd_models(message: Message) -> None:
    user_models = await db.get_user_models(message.from_user.id)
    all_models = await db.get_all_models()
    selected = [m.model_id for m in user_models]
    await message.answer(
        "Выбери модели для мониторинга. Уведомления приходят только о выгодных предложениях.",
        reply_markup=get_models_keyboard(selected, all_models),
    )


@router.message(Command("city"))
@error_handler
async def cmd_city(message: Message) -> None:
    cities = await db.get_cities(message.from_user.id)
    await message.answer(
        f"Текущие города: <b>{', '.join(cities)}</b>\n\n"
        f"Выбери города для мониторинга. «Россия» работает по всей стране и не сочетается с конкретными городами.",
        reply_markup=get_city_keyboard(cities, settings.CITIES, settings.CITIES_PER_PAGE, page=0),
    )


@router.message(Command("favorites"))
@error_handler
async def cmd_favorites(message: Message) -> None:
    favorites = await db.get_favorites(message.from_user.id)
    if not favorites:
        await message.answer("В избранном пусто.")
        return

    await message.answer(f"⭐ Избранное ({len(favorites)}):")
    for fav in favorites[:10]:
        import html

        price_str = f"{fav['price']}₽" if fav["price"] else "Цена не указана"
        text = (
            f"<b>{html.escape(fav['title'])}</b>\n"
            f"💰 {price_str}\n"
            f"📍 {html.escape(fav['city'] or 'Россия')}\n"
            f"📁 {html.escape(fav['model_name'])}"
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔗 Открыть", url=fav["url"]),
                    InlineKeyboardButton(
                        text="❌ Удалить",
                        callback_data=FavoriteCB(
                            action="remove", listing_id=fav["listing_id"]
                        ).pack(),
                    ),
                ]
            ]
        )
        await message.answer(text, reply_markup=keyboard)
        await asyncio.sleep(0.1)

    if len(favorites) > 10:
        await message.answer(f"Показаны первые 10 из {len(favorites)}.")
