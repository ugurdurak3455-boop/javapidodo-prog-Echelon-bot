"""
handlers/admin.py — команды администратора (доступны только ADMIN_USER_ID):
                     /validation, /models_list, /set_median, /recalculate_medians,
                     /export_validation
"""

import csv
import logging
import os
from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message

import database as db
from config import settings
from utils.helpers import error_handler

logger = logging.getLogger(__name__)
router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id == settings.ADMIN_ID


@router.message(Command("validation"))
@error_handler
async def cmd_validation(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    stats = await db.get_validation_stats(days=7)
    text = (
        f"<b>Статистика за 7 дней</b>\n\n"
        f"Уведомлений: <b>{stats['total']}</b>\n"
        f"Ложных срабатываний: <b>{stats['fp']}</b>\n"
        f"Точность: <b>{stats['accuracy']}%</b>\n"
        f"Средняя выгода: <b>{stats['avg_discount']}%</b>"
    )
    if stats.get("by_model"):
        text += "\n\n<b>По моделям:</b>\n"
        text += "\n".join(f"• {name}: {count}" for name, count in stats["by_model"])
    await message.answer(text)


@router.message(Command("set_median"))
@error_handler
async def cmd_set_median(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer('Формат: /set_median "Название модели" 25000')
        return

    model_name = parts[1].strip('"')
    try:
        new_median = int(parts[2])
    except ValueError:
        await message.answer("Медиана должна быть числом.")
        return

    model = await db.get_model_by_name(model_name)
    if not model:
        await message.answer(f"Модель «{model_name}» не найдена.")
        return

    old_median = model.median_price
    await db.update_model_median(model.model_id, new_median)
    change = (new_median - old_median) / old_median * 100 if old_median else 0

    import html

    await message.answer(
        f"✅ Медиана обновлена: <b>{html.escape(model_name)}</b>\n"
        f"{old_median}₽ → {new_median}₽ ({change:+.1f}%)"
    )
    logger.info(f"Median set: {model_name} {old_median} -> {new_median}")


@router.message(Command("export_validation"))
@error_handler
async def cmd_export_validation(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    logs = await db.export_validation_log(days=30)
    if not logs:
        await message.answer("Нет данных за последние 30 дней.")
        return

    filename = f"validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    tmp_dir = os.path.join("storage", "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    filepath = os.path.join(tmp_dir, filename)

    fields = [
        "log_id",
        "user_id",
        "listing_id",
        "model_name",
        "price",
        "median_price",
        "discount_percent",
        "notified_at",
        "user_feedback",
        "is_false_positive",
    ]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(logs)

    try:
        await message.answer_document(
            FSInputFile(filepath),
            caption=f"Лог валидации за 30 дней — {len(logs)} записей",
        )
    finally:
        try:
            os.remove(filepath)
        except FileNotFoundError:
            pass
    logger.info(f"Export: {len(logs)} logs (admin {message.from_user.id})")


@router.message(Command("models_list"))
@error_handler
async def cmd_models_list(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    models = await db.get_all_models()
    lines = []
    for m in models:
        lines.append(
            f"<b>{m.name}</b> ({m.category})\n"
            f"Цены: {m.price_min}–{m.price_max}₽, медиана {m.median_price}₽, порог −{m.discount_threshold}%\n"
            f"Обновлена: {m.last_update}"
        )
        
    # Split into chunks of ~4000 characters to respect Telegram limits
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) + 2 > 4000:
            await message.answer(chunk)
            chunk = line
        else:
            chunk += "\n\n" + line if chunk else line
            
    if chunk:
        await message.answer(chunk)


@router.message(Command("recalculate_medians"))
@error_handler
async def cmd_recalculate_medians(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    await message.answer("Пересчитываю медианы...")
    models = await db.get_all_models()
    updated = skipped = 0

    for model in models:
        new_median = await db.calculate_median_for_model(model.model_id, days=7)
        if new_median is None:
            skipped += 1
            continue
        old = model.median_price
        await db.update_model_median(model.model_id, new_median)
        change = (new_median - old) / old * 100 if old else 0
        logger.info(f"Медиана «{model.name}»: {old}₽ → {new_median}₽ ({change:+.1f}%)")
        updated += 1

    await message.answer(f"✅ Готово: обновлено {updated}, пропущено {skipped} (мало данных)")
    logger.info(f"Medians: updated {updated}, skipped {skipped}")


@router.message(Command("reports"))
@error_handler
async def cmd_reports(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    reports = await db.get_pending_reports()
    if not reports:
        await message.answer("Нет активных жалоб.")
        return

    import html

    text = f"<b>Активные жалобы ({len(reports)}):</b>\n\n"
    for r in reports[:10]:
        text += (
            f"ID жалобы: {r['report_id']}\n"
            f"Пользователь: {r['user_id']}\n"
            f'Товар: <a href="{r["url"]}">{html.escape(r["title"])}</a>\n'
            f"Причина: {html.escape(r['reason'] or '')}\n"
            f"Дата: {r['created_at']}\n\n"
        )

    await message.answer(text, disable_web_page_preview=True)
