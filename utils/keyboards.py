"""
utils/keyboards.py — фабрики inline-клавиатур и CallbackData-схемы.
                      Все кнопки бота собираются здесь.
"""

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from pydantic import ConfigDict

import database as db
from config import settings


class ModelCB(CallbackData, prefix="model"):
    model_config = ConfigDict(protected_namespaces=())
    action: str
    model_id: int


class ActionCB(CallbackData, prefix="action"):
    action: str


class CityCB(CallbackData, prefix="city"):
    name: str


class CityPageCB(CallbackData, prefix="citypage"):
    page: int


class FavoriteCB(CallbackData, prefix="fav"):
    action: str
    listing_id: str


class NotificationCB(CallbackData, prefix="notif"):
    model_config = ConfigDict(protected_namespaces=())
    action: str
    model_name: str


class ListingNavCB(CallbackData, prefix="listnav"):
    model_config = ConfigDict(protected_namespaces=())
    action: str
    model_name: str
    index: int


class ReportCB(CallbackData, prefix="report"):
    action: str
    listing_id: str


def get_close_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Закрыть", callback_data="close_msg")]]
    )


def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Мои фильтры"), KeyboardButton(text="⭐ Избранное")],
            [KeyboardButton(text="🏢 Города"), KeyboardButton(text="📱 Модели")],
            [KeyboardButton(text="⚙️ Настройки")],
        ],
        resize_keyboard=True,
    )


class SettingsCB(CallbackData, prefix="set"):
    action: str
    value: int = 0

def get_settings_keyboard(min_discount: int, dnd_enabled: bool) -> InlineKeyboardMarkup:
    dnd_text = "ВКЛ 🌙" if dnd_enabled else "ВЫКЛ ☀️"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🔔 Порог выгоды: >{min_discount}%", callback_data=SettingsCB(action="discount").pack())],
            [InlineKeyboardButton(text=f"🔇 Тихие часы (23:00-07:00): {dnd_text}", callback_data=SettingsCB(action="dnd").pack())],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_msg")]
        ]
    )


def get_models_keyboard(
    user_model_ids: list[int], all_models: list[db.Model]
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for model in all_models:
        is_dict = isinstance(model, dict)
        model_id = model["model_id"] if is_dict else model.model_id
        name = model["name"] if is_dict else model.name
        category = model["category"] if is_dict else model.category
        price_min = model["price_min"] if is_dict else model.price_min
        price_max = model["price_max"] if is_dict else model.price_max
        discount_threshold = model["discount_threshold"] if is_dict else model.discount_threshold

        check = "✅ " if model_id in user_model_ids else ""
        label = f"{check}{name} ({category}, {price_min}–{price_max}₽, −{discount_threshold}%)"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=ModelCB(action="toggle", model_id=model_id).pack(),
                )
            ]
        )

    if user_model_ids:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🗑 Очистить все",
                    callback_data=ActionCB(action="clear_all_models").pack(),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="✅ Готово",
                callback_data=ActionCB(action="finish_models").pack(),
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_city_keyboard(
    current_cities: list[str], available_cities: list[str], cities_per_page: int, page: int = 0
) -> InlineKeyboardMarkup:
    total_pages = max(1, (len(available_cities) + cities_per_page - 1) // cities_per_page)
    start = page * cities_per_page
    end = min(start + cities_per_page, len(available_cities))

    rows: list[list[InlineKeyboardButton]] = []
    for city in available_cities[start:end]:
        check = "✅ " if city in current_cities else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{check}{city}",
                    callback_data=CityCB(name=city).pack(),
                )
            ]
        )

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data=CityPageCB(page=page - 1).pack(),
            )
        )
    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(
                text="Вперед ▶️",
                callback_data=CityPageCB(page=page + 1).pack(),
            )
        )
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="📥 Готово", callback_data="city_finish")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
