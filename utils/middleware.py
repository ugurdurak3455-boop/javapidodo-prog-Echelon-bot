"""
utils/middleware.py — middleware для Dispatcher:
                       RateLimitMiddleware — защита от спама (0.5 сек между запросами),
                       AutoRegisterMiddleware — авторегистрация новых пользователей в БД.
"""

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject

import database as db

logger = logging.getLogger(__name__)

BLOCK_DURATION = 300


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, limit: float = 0.5):
        self.limit = limit
        self.last_call: dict[int, float] = {}

    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if not user:
            return await handler(event, data)

        now = time.time()
        if now - self.last_call.get(user.id, 0) < self.limit:
            if isinstance(event, CallbackQuery):
                await event.answer("Слишком часто!", show_alert=False)
            return

        self.last_call[user.id] = now

        return await handler(event, data)


class AutoRegisterMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            actual_event = getattr(event, "event", event)
            user = getattr(actual_event, "from_user", None)

        user_id = user.id if user else None
        if user_id:
            try:
                await db.register_user(user_id)
                await db.set_user_active(user_id, True)
            except Exception:
                logger.exception(f"Ошибка при регистрации/активации пользователя {user_id}")

        return await handler(event, data)
