"""
handlers/callbacks.py — обработчики нажатий на inline-кнопки:
                         выбор моделей, городов, просмотр/скрытие объявлений,
                         добавление в избранное, реакции на уведомления.
"""

import logging

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

import database as db
from config import settings
from utils.helpers import HELP_TEXT, error_handler, get_status_text
from utils.keyboards import (
    ActionCB,
    CityCB,
    CityPageCB,
    FavoriteCB,
    ListingNavCB,
    ModelCB,
    NotificationCB,
    ReportCB,
    ReportCB,
    get_close_keyboard,
    get_city_keyboard,
    get_models_keyboard,
)
from utils.state import user_states

logger = logging.getLogger(__name__)
router = Router()


async def _user_limits(user_id: int) -> tuple[int, int]:
    user = await db.get_user(user_id)
    tier = user.tier if user else "free"
    return (
        (settings.PREMIUM_LIMITS["models"], settings.PREMIUM_LIMITS["cities"])
        if tier == "premium"
        else (settings.FREE_LIMITS["models"], settings.FREE_LIMITS["cities"])
    )


async def _refresh_models_keyboard(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    user_models = await db.get_user_models(user_id)
    all_models = await db.get_all_models()
    selected = [m.model_id for m in user_models]
    await callback.message.edit_reply_markup(reply_markup=get_models_keyboard(selected, all_models))


@router.callback_query(ModelCB.filter(F.action == "toggle"))
@error_handler
async def cb_toggle_model(callback: CallbackQuery, callback_data: ModelCB) -> None:
    user_id = callback.from_user.id
    model = await db.get_model_by_id(callback_data.model_id)
    if not model:
        return await callback.answer("Не найдено", show_alert=True)

    user_models = await db.get_user_models(user_id)
    limit, _ = await _user_limits(user_id)

    if not any(m.model_id == model.model_id for m in user_models) and len(user_models) >= limit:
        return await callback.answer(f"Лимит: {limit} моделей", show_alert=True)

    added = await db.toggle_user_model(user_id, model.model_id)
    await callback.answer(f"{'✅' if added else '❌'} {model.name}")
    await _refresh_models_keyboard(callback)


@router.callback_query(ActionCB.filter(F.action == "clear_all_models"))
@error_handler
async def cb_clear_all_models(callback: CallbackQuery) -> None:
    await db.clear_user_models(callback.from_user.id)
    await callback.answer("Все модели удалены")
    await _refresh_models_keyboard(callback)


@router.callback_query(ActionCB.filter(F.action == "finish_models"))
@error_handler
async def cb_finish_models(callback: CallbackQuery) -> None:
    user_models = await db.get_user_models(callback.from_user.id)

    if not user_models:
        await callback.message.edit_text(
            "Вы не выбрали ни одной модели. Мониторинг приостановлен.",
            reply_markup=get_close_keyboard(),
        )
        await callback.answer()
        return

    await db.request_scan(callback.from_user.id)
    names = ", ".join(m.name for m in user_models)

    await callback.message.edit_text(
        f"✅ <b>Выбор принят!</b>\n\n"
        f"Модели: <b>{names}</b>\n\n"
        f"Парсер запущен. Первые результаты придут автоматически.\n"
        f"<i>(Для Free-аккаунтов действует задержка 5 минут)</i>",
        parse_mode="HTML",
        reply_markup=get_close_keyboard(),
    )
    await callback.answer("Сохранено")


@router.callback_query(CityCB.filter())
@error_handler
async def cb_select_city(callback: CallbackQuery, callback_data: CityCB) -> None:
    city = callback_data.name
    if city not in settings.CITIES:
        await callback.answer("Неизвестный город", show_alert=True)
        return

    current = await db.get_cities(callback.from_user.id)
    if city == "Россия":
        new_cities = ["Россия"]
    elif city in current:
        current.remove(city)
        new_cities = current or ["Россия"]
    elif "Россия" in current:
        new_cities = [city]
    else:
        _model_limit, city_limit = await _user_limits(callback.from_user.id)
        if len(current) >= city_limit:
            await callback.answer(
                f"Лимит: максимум {city_limit} город(а).",
                show_alert=True,
            )
            return
        new_cities = current + [city]

    await db.set_cities(callback.from_user.id, new_cities)
    await callback.message.edit_text(
        f"Текущие города: <b>{', '.join(new_cities)}</b>\n\nВыбери города для мониторинга.",
        reply_markup=get_city_keyboard(
            new_cities, settings.CITIES, settings.CITIES_PER_PAGE, page=0
        ),
    )
    await callback.answer()


@router.callback_query(CityPageCB.filter())
@error_handler
async def cb_city_page(callback: CallbackQuery, callback_data: CityPageCB) -> None:
    cities = await db.get_cities(callback.from_user.id)
    await callback.message.edit_text(
        f"Текущие города: <b>{', '.join(cities)}</b>\n\nВыбери города для мониторинга.",
        reply_markup=get_city_keyboard(
            cities, settings.CITIES, settings.CITIES_PER_PAGE, page=callback_data.page
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "city_finish")
@error_handler
async def cb_city_finish(callback: CallbackQuery) -> None:
    cities = await db.get_cities(callback.from_user.id)
    await callback.message.edit_text(
        f"✅ Города сохранены: <b>{', '.join(cities)}</b>", reply_markup=get_close_keyboard()
    )
    await callback.answer()


async def _show_listing(
    message: Message, user_id: int, model_name: str, index: int, listings: list
) -> None:
    import html

    listing = listings[index]
    price_str = f"{listing['price']}₽" if listing["price"] else "Цена не указана"
    median = listing.get("median_at_time") or 0
    discount = listing.get("discount_percent") or 0

    discount_emoji = "🟢" if discount >= 15 else "🟡" if discount > 0 else "⚪"
    text = f"📦 <b>{html.escape(listing['title'])}</b>\n\n"
    text += f"💰 Цена: <b>{price_str}</b>\n"
    if median > 0:
        text += f"📊 Медиана: <i>{median}₽</i>\n"
        text += f"🔥 Выгода: {discount_emoji} <b>{discount}%</b>\n"
    text += f"\n📍 Город: {html.escape(listing.get('city', 'Россия'))}\n\n"
    text += f"<i>Объявление {index + 1} из {len(listings)}</i>"

    nav = []
    if index > 0:
        nav.append(
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data=ListingNavCB(
                    action="prev", model_name=model_name, index=index
                ).pack(),
            )
        )
    nav.append(
        InlineKeyboardButton(
            text="❌ Закрыть",
            callback_data=ListingNavCB(action="exit", model_name=model_name, index=index).pack(),
        )
    )
    if index < len(listings) - 1:
        nav.append(
            InlineKeyboardButton(
                text="Вперед ▶️",
                callback_data=ListingNavCB(
                    action="next", model_name=model_name, index=index
                ).pack(),
            )
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            nav,
            [
                InlineKeyboardButton(
                    text="📈 История цен",
                    callback_data=ListingNavCB(
                        action="history", model_name=model_name, index=index
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⭐ В избранное",
                    callback_data=FavoriteCB(action="add", listing_id=listing["listing_id"]).pack(),
                ),
                InlineKeyboardButton(
                    text="⚠️ Пожаловаться",
                    callback_data=ReportCB(
                        action="false_positive", listing_id=listing["listing_id"]
                    ).pack(),
                ),
            ],
            [InlineKeyboardButton(text="🔗 Открыть на Avito", url=listing["url"])],
        ]
    )

    image_url = listing.get("image_url")

    try:
        if image_url:
            if message.photo:
                await message.edit_media(
                    media=InputMediaPhoto(media=image_url, caption=text, parse_mode="HTML"),
                    reply_markup=keyboard,
                )
            else:
                await message.delete()
                await message.answer_photo(photo=image_url, caption=text, reply_markup=keyboard)
        else:
            if message.photo:
                await message.delete()
                await message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)
            else:
                await message.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)
    except Exception as e:
        logger.debug(f"Error updating message: {e}")
        try:
            await message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)
        except:
            pass

    await db.mark_listing_sent(user_id, listing["listing_id"])


@router.callback_query(ReportCB.filter(F.action == "false_positive"))
@error_handler
async def cb_report_false_positive(callback: CallbackQuery, callback_data: ReportCB) -> None:
    await db.update_validation_feedback(
        user_id=callback.from_user.id,
        listing_id=callback_data.listing_id,
        is_false_positive=True,
        feedback="Пользователь отметил как ложное срабатывание через бота",
    )
    await db.report_listing(
        user_id=callback.from_user.id,
        listing_id=callback_data.listing_id,
        reason="Ложное срабатывание",
    )
    await callback.answer("🙏 Спасибо! Мы учтём это для улучшения точности.", show_alert=True)

    try:
        new_markup = callback.message.reply_markup

        new_rows = []
        for row in new_markup.inline_keyboard:
            new_row = [btn for btn in row if "report" not in btn.callback_data]
            if new_row:
                new_rows.append(new_row)
        await callback.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=new_rows)
        )
    except Exception:
        pass


def _user_listings(user_id: int, model_name: str) -> list:
    return user_states.get(user_id, {}).get(f"listings_{model_name}", [])


def _drop_user_listings(user_id: int, model_name: str) -> None:
    user_states.get(user_id, {}).pop(f"listings_{model_name}", None)


async def _mark_all_sent(user_id: int, listings: list) -> None:
    for listing in listings:
        await db.mark_listing_sent(user_id, listing["listing_id"])


@router.callback_query(NotificationCB.filter(F.action == "show"))
@error_handler
async def cb_show_listings(callback: CallbackQuery, callback_data: NotificationCB) -> None:
    listings = _user_listings(callback.from_user.id, callback_data.model_name)
    if not listings:
        await callback.answer("Объявления не найдены", show_alert=True)
        return
    await _show_listing(
        callback.message, callback.from_user.id, callback_data.model_name, 0, listings
    )
    await callback.answer()


@router.callback_query(NotificationCB.filter(F.action == "skip"))
@error_handler
async def cb_skip_listings(callback: CallbackQuery, callback_data: NotificationCB) -> None:
    user_id = callback.from_user.id
    listings = _user_listings(user_id, callback_data.model_name)
    await _mark_all_sent(user_id, listings)
    _drop_user_listings(user_id, callback_data.model_name)
    await callback.message.edit_text(
        f"✅ Объявления по модели <b>{callback_data.model_name}</b> пропущены"
    )
    await callback.answer("Пропущено")


@router.callback_query(ListingNavCB.filter())
@error_handler
async def cb_listing_navigation(callback: CallbackQuery, callback_data: ListingNavCB) -> None:
    user_id = callback.from_user.id
    model_name = callback_data.model_name
    listings = _user_listings(user_id, model_name)
    if not listings:
        await callback.answer("Объявления не найдены", show_alert=True)
        return

    match callback_data.action:
        case "exit":
            await _mark_all_sent(user_id, listings)
            _drop_user_listings(user_id, model_name)
            await callback.message.edit_text("✅ Просмотр завершён.")
            await callback.answer()
            return

        case "history":
            model = await db.get_model_by_name(model_name)
            if not model:
                return await callback.answer("Не найдено")

            history = await db.get_price_history(model.model_id, days=30)
            if not history:
                return await callback.answer("История цен пуста", show_alert=True)

            daily_prices: dict[str, list[int]] = {}
            for h in history:
                date = (
                    h["recorded_at"][:10]
                    if isinstance(h["recorded_at"], str)
                    else h["recorded_at"].strftime("%Y-%m-%d")
                )
                daily_prices.setdefault(date, []).append(h["price"])

            lines = []
            for date in sorted(daily_prices.keys(), reverse=True)[:10]:
                prices = daily_prices[date]
                avg = sum(prices) // len(prices)
                lines.append(f"📅 {date}: ~<b>{avg}₽</b>")

            history_text = "\n".join(lines)
            await callback.answer()
            await callback.message.answer(
                f"📈 <b>История цен: {model_name}</b>\n(за последние 30 дней)\n\n{history_text}",
                parse_mode="HTML",
            )
            return

        case "next":
            new_index = min(callback_data.index + 1, len(listings) - 1)
        case _:
            new_index = max(callback_data.index - 1, 0)

    await _show_listing(callback.message, user_id, model_name, new_index, listings)
    await callback.answer()


@router.callback_query(FavoriteCB.filter(F.action == "add"))
@error_handler
async def cb_add_favorite(callback: CallbackQuery, callback_data: FavoriteCB) -> None:
    await db.add_favorite(callback.from_user.id, callback_data.listing_id)
    await callback.answer("⭐ Добавлено в избранное")


@router.callback_query(FavoriteCB.filter(F.action == "remove"))
@error_handler
async def cb_remove_favorite(callback: CallbackQuery, callback_data: FavoriteCB) -> None:
    await db.remove_favorite(callback.from_user.id, callback_data.listing_id)
    await callback.message.delete()
    await callback.answer("Удалено из избранного")


from utils.keyboards import SettingsCB, get_settings_keyboard

@router.callback_query(SettingsCB.filter())
@error_handler
async def cb_settings(callback: CallbackQuery, callback_data: SettingsCB) -> None:
    user = await db.get_user(callback.from_user.id)
    if not user:
        return

    if callback_data.action == "discount":
        new_val = (user.min_discount + 5) % 30
        await db.update_user_setting(user.user_id, "min_discount", new_val)
        user.min_discount = new_val
    elif callback_data.action == "dnd":
        new_val = not user.dnd_enabled
        await db.update_user_setting(user.user_id, "dnd_enabled", new_val)
        user.dnd_enabled = new_val

    kb = get_settings_keyboard(user.min_discount, user.dnd_enabled)
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "close_msg")
@error_handler
async def cb_close_msg(callback: CallbackQuery) -> None:
    await callback.message.delete()
    await callback.answer()
