import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings

db_retry = retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))


class User(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    user_id: int
    is_active: bool = True
    tier: str = Field(default="free", alias="subscription_tier")
    city: str = "Россия"
    joined_at: datetime
    scan_requested_at: datetime | None = None
    min_discount: int = 0
    dnd_enabled: bool = False

    def __getitem__(self, item: str) -> Any:
        if item == "subscription_tier":
            return self.tier
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)


class Model(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    model_id: int
    name: str
    category: str
    keywords: list[str]
    stop_words: list[str]
    price_min: int
    price_max: int
    median_price: int
    discount_threshold: int
    search_url: str | None = Field(None, alias="avito_search_url")
    last_update: datetime = Field(alias="last_median_update")

    def __getitem__(self, item: str) -> Any:
        if item == "avito_search_url":
            return self.search_url
        if item == "last_median_update":
            return self.last_update
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "Model":
        data = dict(row)
        for key in ["keywords", "stop_words"]:
            if isinstance(data.get(key), str):
                try:
                    data[key] = json.loads(data[key])
                except json.JSONDecodeError:
                    data[key] = [v.strip() for v in data[key].split(",") if v.strip()]
        return cls.model_validate(data)


DB_PATH = settings.DB_PATH
_db: aiosqlite.Connection | None = None


async def _configure_db(db: aiosqlite.Connection) -> None:
    db.row_factory = aiosqlite.Row
    await db.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        PRAGMA cache_size=-64000;
        PRAGMA foreign_keys=ON;
    """)
    # Migrations
    try:
        await db.execute("ALTER TABLE users ADD COLUMN min_discount INTEGER NOT NULL DEFAULT 0")
        await db.execute("ALTER TABLE users ADD COLUMN dnd_enabled INTEGER NOT NULL DEFAULT 0")
        await db.commit()
    except Exception:
        pass


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        path = Path(DB_PATH).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        _db = await aiosqlite.connect(DB_PATH, timeout=15.0)
        await _configure_db(_db)
    return _db


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None


@asynccontextmanager
async def db_session() -> AsyncGenerator[aiosqlite.Connection]:
    global _db
    if _db is not None:
        yield _db
    else:
        path = Path(DB_PATH).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(DB_PATH, timeout=15.0) as db:
            await _configure_db(db)
            yield db


async def init_db() -> None:
    async with db_session() as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                is_active INTEGER NOT NULL DEFAULT 1,
                subscription_tier TEXT NOT NULL DEFAULT 'free',
                city TEXT NOT NULL DEFAULT 'Россия',
                joined_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                scan_requested_at TIMESTAMP,
                min_discount INTEGER NOT NULL DEFAULT 0,
                dnd_enabled INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS models (
                model_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                keywords TEXT NOT NULL,
                stop_words TEXT NOT NULL,
                price_min INTEGER NOT NULL,
                price_max INTEGER NOT NULL,
                median_price INTEGER NOT NULL,
                discount_threshold INTEGER NOT NULL,
                avito_search_url TEXT,
                last_median_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS user_models (
                user_id INTEGER NOT NULL,
                model_id INTEGER NOT NULL,
                added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, model_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (model_id) REFERENCES models(model_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS listings (
                listing_id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                price INTEGER NOT NULL DEFAULT 0,
                model_id INTEGER NOT NULL,
                city TEXT NOT NULL DEFAULT 'Россия',
                image_url TEXT,
                description_preview TEXT NOT NULL DEFAULT '',
                median_at_time INTEGER NOT NULL DEFAULT 0,
                discount_percent INTEGER NOT NULL DEFAULT 0,
                parsed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models(model_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS sent_listings (
                user_id INTEGER NOT NULL,
                listing_id TEXT NOT NULL,
                sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, listing_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (listing_id) REFERENCES listings(listing_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS hidden_listings (
                user_id INTEGER NOT NULL,
                listing_id TEXT NOT NULL,
                hidden_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, listing_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS favorites (
                user_id INTEGER NOT NULL,
                listing_id TEXT NOT NULL,
                added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, listing_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS reports (
                report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                listing_id TEXT NOT NULL,
                reason TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS validation_log (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                listing_id TEXT NOT NULL,
                model_name TEXT NOT NULL,
                price INTEGER NOT NULL,
                median_price INTEGER NOT NULL,
                discount_percent INTEGER NOT NULL,
                notified_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                user_feedback TEXT,
                is_false_positive INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS price_history (
                history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id INTEGER NOT NULL,
                price INTEGER NOT NULL,
                city TEXT NOT NULL,
                recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES models(model_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)

        await db.executescript("""
            CREATE INDEX IF NOT EXISTS idx_user_models_user ON user_models(user_id);
            CREATE INDEX IF NOT EXISTS idx_listings_model_date ON listings(model_id, parsed_at DESC);
            CREATE INDEX IF NOT EXISTS idx_listings_parsed_at ON listings(parsed_at);
            CREATE INDEX IF NOT EXISTS idx_sent_listings_user ON sent_listings(user_id);
            CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id);
        """)


@db_retry
async def init_models_from_config() -> None:
    from models_config import PREDEFINED_MODELS

    async with db_session() as db:
        for m in PREDEFINED_MODELS:
            kw = json.dumps(m["keywords"], ensure_ascii=False)
            sw = json.dumps(m["stop_words"], ensure_ascii=False)
            await db.execute(
                """INSERT OR IGNORE INTO models
                   (name, category, keywords, stop_words, price_min, price_max,
                    median_price, discount_threshold, avito_search_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    m["name"],
                    m["category"],
                    kw,
                    sw,
                    m["price_min"],
                    m["price_max"],
                    m["initial_median"],
                    m["discount_threshold"],
                    m["avito_search_url"],
                ),
            )
        await db.commit()


@db_retry
async def get_user(user_id: int) -> User | None:
    async with db_session() as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return User.model_validate(dict(row)) if row else None


@db_retry
async def register_user(user_id: int) -> None:
    async with db_session() as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.commit()


@db_retry
async def set_user_active(user_id: int, is_active: bool) -> None:
    async with db_session() as db:
        await db.execute(
            "UPDATE users SET is_active = ? WHERE user_id = ?", (1 if is_active else 0, user_id)
        )
        await db.commit()


@db_retry
async def get_cities(user_id: int) -> list[str]:
    async with db_session() as db:
        async with db.execute("SELECT city FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if not row or not row["city"]:
                return ["Россия"]
            return [c.strip() for c in row["city"].split(",") if c.strip()]


@db_retry
async def set_cities(user_id: int, cities: list[str]) -> None:
    async with db_session() as db:
        val = ",".join(cities) if cities else "Россия"
        await db.execute("UPDATE users SET city = ? WHERE user_id = ?", (val, user_id))
        await db.commit()


@db_retry
async def get_all_models() -> list[Model]:
    async with db_session() as db:
        async with db.execute("SELECT * FROM models ORDER BY name") as cur:
            return [Model.from_row(row) for row in await cur.fetchall()]


@db_retry
async def get_model_by_id(model_id: int) -> Model | None:
    async with db_session() as db:
        async with db.execute("SELECT * FROM models WHERE model_id = ?", (model_id,)) as cur:
            row = await cur.fetchone()
            return Model.from_row(row) if row else None


@db_retry
async def get_model_by_name(name: str) -> Model | None:
    async with db_session() as db:
        async with db.execute("SELECT * FROM models WHERE name = ?", (name,)) as cur:
            row = await cur.fetchone()
            return Model.from_row(row) if row else None


@db_retry
async def get_user_models(user_id: int) -> list[Model]:
    async with db_session() as db:
        async with db.execute(
            """
            SELECT m.* FROM models m
            INNER JOIN user_models um ON m.model_id = um.model_id
            WHERE um.user_id = ? ORDER BY m.name
        """,
            (user_id,),
        ) as cur:
            return [Model.from_row(row) for row in await cur.fetchall()]


@db_retry
async def toggle_user_model(user_id: int, model_id: int) -> bool:
    async with db_session() as db:
        async with db.execute(
            "SELECT 1 FROM user_models WHERE user_id=? AND model_id=?", (user_id, model_id)
        ) as cur:
            if await cur.fetchone():
                await db.execute(
                    "DELETE FROM user_models WHERE user_id=? AND model_id=?", (user_id, model_id)
                )
                await db.commit()
                return False
            await db.execute(
                "INSERT INTO user_models (user_id, model_id) VALUES (?, ?)", (user_id, model_id)
            )
            await db.commit()
            return True


@db_retry
async def clear_user_models(user_id: int) -> None:
    async with db_session() as db:
        await db.execute("DELETE FROM user_models WHERE user_id = ?", (user_id,))
        await db.commit()


@db_retry
async def save_listings(items: list[dict]) -> int:
    async with db_session() as db:
        new = 0
        for item in items:
            mid = item.get("model_id")
            if not mid:
                continue
            async with db.execute(
                "SELECT median_price FROM models WHERE model_id = ?", (mid,)
            ) as cur:
                row = await cur.fetchone()
                if not row:
                    continue
                median = row["median_price"]

            p = item.get("price", 0)
            disc = int(((median - p) / median) * 100) if p > 0 and median > p else 0
            try:
                cur = await db.execute(
                    """
                    INSERT OR IGNORE INTO listings 
                    (listing_id, url, title, price, model_id, city, image_url, description_preview, median_at_time, discount_percent)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        str(item["id"]),
                        item["url"],
                        item["title"],
                        p,
                        mid,
                        item.get("city", "Россия"),
                        item.get("image_url"),
                        item.get("description_preview", ""),
                        median,
                        disc,
                    ),
                )
                if cur.rowcount > 0:
                    new += 1
            except Exception as e:
                logger.debug(f"Save ignored {item.get('id')}: {e}")
        await db.commit()
        return new


@db_retry
async def get_new_listings_for_user(user_id: int) -> list[dict]:
    user = await get_user(user_id)
    if not user:
        return []
    cities = await get_cities(user_id)

    if settings.BYPASS_DELAY:
        time_filter = "datetime('now', '+1 hour')"
    else:
        time_filter = (
            "datetime('now')" if user.tier == "premium" else "datetime('now', '-5 minutes')"
        )
    sql = f"""
        SELECT l.*, m.name AS model_name FROM listings l
        JOIN models m ON l.model_id = m.model_id
        JOIN user_models um ON l.model_id = um.model_id
        WHERE um.user_id = ? AND l.parsed_at <= {time_filter}
          AND l.discount_percent >= MAX(m.discount_threshold, ?)
          AND NOT EXISTS (SELECT 1 FROM sent_listings sl WHERE sl.listing_id = l.listing_id AND sl.user_id = ?)
          AND NOT EXISTS (SELECT 1 FROM hidden_listings hl WHERE hl.listing_id = l.listing_id AND hl.user_id = ?)
    """
    params: list[Any] = [user_id, getattr(user, 'min_discount', 0), user_id, user_id]
    if "Россия" not in cities:
        sql += f" AND l.city IN ({','.join(['?'] * len(cities))})"
        params += cities
    sql += " ORDER BY l.discount_percent DESC, l.parsed_at DESC LIMIT 50"
    async with db_session() as db:
        async with db.execute(sql, params) as cur:
            return [dict(row) for row in await cur.fetchall()]


@db_retry
async def mark_listing_sent(user_id: int, listing_id: str) -> None:
    async with db_session() as db:
        await db.execute(
            "INSERT OR IGNORE INTO sent_listings (user_id, listing_id) VALUES (?, ?)",
            (user_id, listing_id),
        )
        await db.commit()


@db_retry
async def mark_listings_sent(user_id: int, listing_ids: list[str]) -> None:
    if not listing_ids:
        return
    async with db_session() as db:
        await db.executemany(
            "INSERT OR IGNORE INTO sent_listings (user_id, listing_id) VALUES (?, ?)",
            [(user_id, lid) for lid in listing_ids],
        )
        await db.commit()


@db_retry
async def update_model_median(model_id: int, new_median: int) -> None:
    async with db_session() as db:
        await db.execute(
            "UPDATE models SET median_price = ?, last_median_update = CURRENT_TIMESTAMP WHERE model_id = ?",
            (new_median, model_id),
        )
        await db.commit()


@db_retry
async def calculate_median_for_model(model_id: int, days: int = 7) -> int | None:
    async with db_session() as db:
        async with db.execute(
            "SELECT price FROM listings WHERE model_id = ? AND price > 0 AND parsed_at >= datetime('now', ?) ORDER BY price",
            (model_id, f"-{days} days"),
        ) as cur:
            prices = [row["price"] for row in await cur.fetchall()]
    if len(prices) < 10:
        return None
    n = len(prices)
    return (prices[n // 2 - 1] + prices[n // 2]) // 2 if n % 2 == 0 else prices[n // 2]


@db_retry
async def cleanup_listings(days: int = 30) -> int:
    async with db_session() as db:
        await db.execute(
            "INSERT INTO price_history (model_id, price, city, recorded_at) SELECT model_id, price, city, parsed_at FROM listings WHERE parsed_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        async with db.execute(
            "DELETE FROM listings WHERE parsed_at < datetime('now', ?)", (f"-{days} days",)
        ) as cur:
            await db.commit()
            return cur.rowcount

@db_retry
async def cleanup_old_history_and_logs(days_history: int = 180, days_logs: int = 90) -> tuple[int, int]:
    async with db_session() as db:
        async with db.execute(
            "DELETE FROM price_history WHERE recorded_at < datetime('now', ?)", (f"-{days_history} days",)
        ) as cur1:
            hist_deleted = cur1.rowcount
            
        async with db.execute(
            "DELETE FROM validation_log WHERE notified_at < datetime('now', ?)", (f"-{days_logs} days",)
        ) as cur2:
            logs_deleted = cur2.rowcount
            
        await db.commit()
        return hist_deleted, logs_deleted


@db_retry
async def cleanup_inactive_users(days: int = 180) -> int:
    async with db_session() as db:
        async with db.execute(
            "DELETE FROM users WHERE user_id NOT IN (SELECT DISTINCT user_id FROM user_models) AND joined_at < datetime('now', ?)",
            (f"-{days} days",),
        ) as cur:
            await db.commit()
            return cur.rowcount


@db_retry
async def request_scan(user_id: int) -> None:
    async with db_session() as db:
        await db.execute(
            "UPDATE users SET scan_requested_at = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,)
        )
        await db.commit()


@db_retry
async def get_users_needing_scan() -> list[int]:
    async with db_session() as db:
        async with db.execute(
            "SELECT user_id FROM users WHERE scan_requested_at IS NOT NULL AND is_active = 1"
        ) as cur:
            return [row["user_id"] for row in await cur.fetchall()]


@db_retry
async def reset_scan_request(user_id: int) -> None:
    async with db_session() as db:
        await db.execute("UPDATE users SET scan_requested_at = NULL WHERE user_id = ?", (user_id,))
        await db.commit()


@db_retry
async def hide_listing(user_id: int, listing_id: str) -> None:
    async with db_session() as db:
        await db.execute(
            "INSERT OR IGNORE INTO hidden_listings (user_id, listing_id) VALUES (?, ?)",
            (user_id, listing_id),
        )
        await db.commit()


@db_retry
async def is_favorite(user_id: int, listing_id: str) -> bool:
    async with db_session() as db:
        async with db.execute(
            "SELECT 1 FROM favorites WHERE user_id = ? AND listing_id = ?", (user_id, listing_id)
        ) as cur:
            return (await cur.fetchone()) is not None


@db_retry
async def add_favorite(user_id: int, listing_id: str) -> None:
    async with db_session() as db:
        await db.execute(
            "INSERT OR IGNORE INTO favorites (user_id, listing_id) VALUES (?, ?)",
            (user_id, listing_id),
        )
        await db.commit()


@db_retry
async def remove_favorite(user_id: int, listing_id: str) -> None:
    async with db_session() as db:
        await db.execute(
            "DELETE FROM favorites WHERE user_id = ? AND listing_id = ?", (user_id, listing_id)
        )
        await db.commit()


@db_retry
async def get_favorites(user_id: int) -> list[dict]:
    async with db_session() as db:
        async with db.execute(
            """
            SELECT l.*, m.name AS model_name, f.added_at FROM favorites f
            INNER JOIN listings l ON f.listing_id = l.listing_id
            INNER JOIN models m ON l.model_id = m.model_id
            WHERE f.user_id = ? ORDER BY f.added_at DESC
        """,
            (user_id,),
        ) as cur:
            return [dict(row) for row in await cur.fetchall()]


@db_retry
async def report_listing(user_id: int, listing_id: str, reason: str | None = None) -> None:
    async with db_session() as db:
        await db.execute(
            "INSERT INTO reports (user_id, listing_id, reason) VALUES (?, ?, ?)",
            (user_id, listing_id, reason),
        )
        await db.commit()


@db_retry
async def get_pending_reports() -> list[dict]:
    async with db_session() as db:
        async with db.execute(
            "SELECT r.*, l.title, l.url FROM reports r LEFT JOIN listings l ON r.listing_id = l.listing_id WHERE r.status = 'pending' ORDER BY r.created_at DESC"
        ) as cur:
            return [dict(row) for row in await cur.fetchall()]


@db_retry
async def log_notification(
    user_id: int, listing_id: str, model_name: str, p: int, m: int, d: int
) -> None:
    async with db_session() as db:
        await db.execute(
            "INSERT INTO validation_log (user_id, listing_id, model_name, price, median_price, discount_percent) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, listing_id, model_name, p, m, d),
        )
        await db.commit()


@db_retry
async def update_validation_feedback(
    user_id: int, listing_id: str, is_false_positive: bool, feedback: str | None = None
) -> None:
    async with db_session() as db:
        await db.execute(
            "UPDATE validation_log SET is_false_positive = ?, user_feedback = ? WHERE user_id = ? AND listing_id = ?",
            (1 if is_false_positive else 0, feedback, user_id, listing_id),
        )
        await db.commit()


@db_retry
async def get_validation_stats(days: int = 7) -> dict:
    async with db_session() as db:
        async with db.execute(
            "SELECT COUNT(*) as total, SUM(is_false_positive) as fp, AVG(discount_percent) as disc FROM validation_log WHERE notified_at >= datetime('now', ?)",
            (f"-{days} days",),
        ) as cur:
            row = await cur.fetchone()
            if row:
                total, fp, disc = (row["total"] or 0), (row["fp"] or 0), (row["disc"] or 0)
            else:
                total, fp, disc = 0, 0, 0

        async with db.execute(
            "SELECT model_name, COUNT(*) as cnt FROM validation_log WHERE notified_at >= datetime('now', ?) GROUP BY model_name ORDER BY cnt DESC",
            (f"-{days} days",),
        ) as cur:
            by_model = [(row["model_name"], row["cnt"]) for row in await cur.fetchall()]

    return {
        "total": total,
        "fp": fp,
        "accuracy": int((total - fp) / total * 100) if total else 0,
        "avg_discount": int(disc),
        "by_model": by_model,
    }


@db_retry
async def export_validation_log(days: int = 30) -> list[dict]:
    async with db_session() as db:
        async with db.execute(
            "SELECT * FROM validation_log WHERE notified_at >= datetime('now', ?)",
            (f"-{days} days",),
        ) as cur:
            return [dict(row) for row in await cur.fetchall()]


@db_retry
async def get_price_history(model_id: int, days: int = 30) -> list[dict]:
    async with db_session() as db:
        sql = "SELECT price, city, recorded_at FROM price_history WHERE model_id = ? AND recorded_at >= datetime('now', ?) UNION ALL SELECT price, city, parsed_at as recorded_at FROM listings WHERE model_id = ? AND parsed_at >= datetime('now', ?) ORDER BY recorded_at ASC"
        async with db.execute(sql, (model_id, f"-{days} days", model_id, f"-{days} days")) as cur:
            return [dict(row) for row in await cur.fetchall()]


@db_retry
async def get_user_savings(user_id: int) -> int:
    async with db_session() as db:
        async with db.execute(
            "SELECT SUM(median_price - price) FROM validation_log WHERE user_id = ? AND is_false_positive = 0",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            return row[0] or 0 if row else 0


@db_retry
async def get_stats() -> dict:
    async with db_session() as db:
        async with db.execute(
            "SELECT SUM(median_price - price) FROM validation_log WHERE is_false_positive = 0"
        ) as cur:
            row = await cur.fetchone()
            total_savings = row[0] or 0 if row else 0
    return {"total_savings": total_savings}


@db_retry
async def get_active_users_with_models() -> list[User]:
    async with db_session() as db:
        async with db.execute("""
            SELECT DISTINCT u.* FROM users u
            JOIN user_models um ON u.user_id = um.user_id
            WHERE u.is_active = 1
        """) as cur:
            return [User.model_validate(dict(row)) for row in await cur.fetchall()]


@db_retry
async def get_users_due_for_scan() -> list[User]:
    return await get_active_users_with_models()


@db_retry
async def mark_user_scanned(user_id: int) -> None:
    await reset_scan_request(user_id)


@db_retry
async def clear_database() -> None:
    async with db_session() as db:
        await db.execute("DELETE FROM sent_listings")
        await db.execute("DELETE FROM hidden_listings")
        await db.execute("DELETE FROM favorites")
        await db.execute("DELETE FROM reports")
        await db.execute("DELETE FROM validation_log")
        await db.execute("DELETE FROM price_history")
        await db.execute("DELETE FROM user_models")
        await db.execute("DELETE FROM listings")
        await db.execute("DELETE FROM users")
        await db.execute("DELETE FROM models")
        await db.execute("DELETE FROM settings")
        await db.commit()
    await init_models_from_config()


@db_retry
async def update_user_setting(user_id: int, setting: str, value: Any) -> None:
    if setting not in ("min_discount", "dnd_enabled"):
        return
    async with db_session() as db:
        await db.execute(f"UPDATE users SET {setting} = ? WHERE user_id = ?", (value, user_id))
        await db.commit()

# optimized median calc
