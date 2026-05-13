import asyncio
import time
from typing import NoReturn

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from loguru import logger

import database as db
from config import settings
from scraper import AvitoBlockedError, AvitoScraper, DemoModelBasedScraper, build_jobs_for_users
from utils.keyboards import NotificationCB
from utils.state import user_states


def limit_jobs_for_cycle(jobs: list[dict], max_jobs: int) -> tuple[list[dict], int]:
    if len(jobs) <= max_jobs:
        return jobs, 0
    return jobs[:max_jobs], len(jobs) - max_jobs


async def cleanup_loop() -> NoReturn:
    while True:
        try:
            del_list = await db.cleanup_listings(settings.RETENTION_DAYS)
            del_users = await db.cleanup_inactive_users(settings.INACTIVE_DAYS)
            del_hist, del_logs = await db.cleanup_old_history_and_logs(days_history=180, days_logs=90)
            logger.info(f"Cleanup: {del_list} listings, {del_users} users, {del_hist} history rows, {del_logs} log rows removed")

            models = await db.get_all_models()
            for m in models:
                if (new_median := await db.calculate_median_for_model(m.model_id)) is not None:
                    await db.update_model_median(m.model_id, new_median)

            await asyncio.sleep(86400)
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            await asyncio.sleep(3600)


async def parser_loop(bot: Bot) -> NoReturn:
    scraper = DemoModelBasedScraper() if settings.MODE == "demo" else AvitoScraper()
    last_parsed: dict[int, float] = {}
    logger.info(f"Parser loop started (mode: {settings.MODE})")
    while True:
        try:
            users = await db.get_users_due_for_scan()
            if not users:
                await asyncio.sleep(15)
                continue

            now = time.time()
            due_users = []
            for user in users:
                # Calculate required delay based on user tier
                delay = (
                    settings.INTERVAL_FREE * 60
                    if user.tier == "free"
                    else settings.INTERVAL_PREMIUM * 60
                )
                
                # Check if enough time has passed OR if a manual scan was requested recently
                if user.scan_requested_at:
                    due_users.append(user)
                elif now - last_parsed.get(user.user_id, 0) >= delay:
                    due_users.append(user)

            if not due_users:
                await asyncio.sleep(15)
                continue

            jobs = await build_jobs_for_users(due_users)

            if jobs:
                active, skipped = limit_jobs_for_cycle(jobs, settings.MAX_JOBS)
                logger.info(f"Parser: starting scan for {len(active)} jobs...")
                try:
                    res = await scraper.run(active)
                    new = await db.save_listings(res)
                    logger.info(
                        f"Parser: scan completed. {len(res)} items found, {new} new listings saved."
                    )
                except AvitoBlockedError:
                    logger.error("Parser: Avito blocked requests. Sending alert to admin.")
                    admin_id = settings.ADMIN_ID
                    if admin_id:
                        try:
                            await bot.send_message(
                                admin_id,
                                "⚠️ <b>Внимание: Блокировка Avito!</b>\n\n"
                                "Бот перестал получать данные с Avito из-за блокировки или устаревания кук.\n"
                                "Пожалуйста, запустите утилиту <b>Captcha Bypass</b> в панели управления Echelon (Control Panel), "
                                "пройдите проверку в браузере и завершите сессию.",
                            )
                        except Exception as send_err:
                            logger.error(f"Failed to send blocked alert to admin: {send_err}")
                    # Увеличиваем задержку до 5 минут при блокировке
                    await asyncio.sleep(300)
                    continue

            for user in due_users:
                await db.mark_user_scanned(user.user_id)
                # If they didn't explicitly request a scan, update their last_parsed time
                if not user.scan_requested_at:
                    last_parsed[user.user_id] = now

            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Parser error: {e}")
            await asyncio.sleep(30)


async def notification_loop(bot: Bot) -> NoReturn:
    last_sent: dict[int, float] = {}
    while True:
        try:
            users = await db.get_active_users_with_models()
            now = time.time()
            for user in users:
                delay = (
                    settings.INTERVAL_FREE * 60
                    if user.tier == "free"
                    else settings.INTERVAL_PREMIUM * 60
                )
                if now - last_sent.get(user.user_id, 0) < delay:
                    continue

                if getattr(user, "dnd_enabled", False):
                    # Moscow time UTC+3
                    from datetime import datetime, timezone, timedelta
                    hour = datetime.now(timezone(timedelta(hours=3))).hour
                    if hour >= 23 or hour < 7:
                        continue

                if listings := await db.get_new_listings_for_user(user.user_id):
                    filtered_listings = [
                        item for item in listings
                        if item.get("discount_percent", 0) >= getattr(user, "min_discount", 0)
                    ]
                    
                    if filtered_listings:
                        await _broadcast(bot, user.user_id, filtered_listings)
                        last_sent[user.user_id] = now
                    
                    # Mark all as sent so we don't process them again
                    await db.mark_listings_sent(user.user_id, [item["listing_id"] for item in listings])
            await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Notify error: {e}")
            await asyncio.sleep(30)


async def _broadcast(bot: Bot, uid: int, listings: list[dict]):
    by_model: dict[str, list[dict]] = {}
    for item in listings:
        by_model.setdefault(item["model_name"], []).append(item)

    for name, group in by_model.items():
        group.sort(key=lambda x: x["discount_percent"], reverse=True)
        user_states[uid][f"listings_{name}"] = group
        best = group[0]

        import html
        
        discount = best.get('discount_percent', 0)
        discount_emoji = "🔥" if discount >= 15 else "🟢" if discount > 0 else "⚪"
        price_formatted = f"{best['price']:,}".replace(',', ' ')
        desc = html.escape(best.get('description_preview', 'Нет описания'))
        if len(desc) > 300:
            desc = desc[:300] + "..."

        text = (
            f"⚡️ <b>Новая находка: {html.escape(name)}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Цена:</b> {price_formatted} ₽\n"
            f"📉 <b>Выгода:</b> {discount_emoji} {discount}% от рынка\n"
            f"🏙 <b>Город:</b> {html.escape(best.get('city', 'Не указан'))}\n\n"
            f"<blockquote expandable><b>Описание:</b>\n"
            f"{desc}</blockquote>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📦 <i>Похожих вариантов в группе: {len(group)}</i>"
        )

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="👁 Показать",
                        callback_data=NotificationCB(action="show", model_name=name).pack(),
                    ),
                    InlineKeyboardButton(
                        text="⏭ Пропустить",
                        callback_data=NotificationCB(action="skip", model_name=name).pack(),
                    ),
                ]
            ]
        )

        try:
            if best.get("image_url"):
                try:
                    await bot.send_photo(uid, photo=best["image_url"], caption=text, reply_markup=kb)
                except TelegramBadRequest:
                    await bot.send_message(uid, text, reply_markup=kb)
            else:
                await bot.send_message(uid, text, reply_markup=kb)
                
            for item in group:
                await db.log_notification(
                    uid,
                    item["listing_id"],
                    name,
                    item["price"],
                    item.get("median_at_time", 0),
                    item.get("discount_percent", 0)
                )

        except (TelegramForbiddenError, TelegramBadRequest):
            await db.set_user_active(uid, False)
            break

        await asyncio.sleep(0.5)
