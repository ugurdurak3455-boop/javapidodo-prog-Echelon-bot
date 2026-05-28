"""
utils/state.py — in-memory состояние пользователей.
                  Хранит последние загруженные списки объявлений (для кнопки «Показать»).
                  Сбрасывается при перезапуске бота — это нормально.
"""

from collections import defaultdict
from typing import Any

user_states: dict[int, dict[str, Any]] = defaultdict(dict)
