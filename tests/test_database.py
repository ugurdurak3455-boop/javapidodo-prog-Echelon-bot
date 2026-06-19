"""Тесты database.py."""

import os
import tempfile
from pathlib import Path

import pytest

import database
from database import (
    add_favorite,
    calculate_median_for_model,
    clear_user_models,
    close_db,
    get_active_users_with_models,
    get_all_models,
    get_cities,
    get_db,
    get_favorites,
    get_model_by_id,
    get_model_by_name,
    get_new_listings_for_user,
    get_user_models,
    hide_listing,
    init_db,
    init_models_from_config,
    is_favorite,
    mark_listing_sent,
    register_user,
    remove_favorite,
    save_listings,
    set_cities,
    toggle_user_model,
    update_model_median,
)


@pytest.fixture
async def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    original = database.DB_PATH
    database.DB_PATH = path
    database._db = None

    await init_db()
    await init_models_from_config()

    try:
        yield path
    finally:
        await close_db()
        database.DB_PATH = original
        database._db = None
        try:
            os.unlink(path)
        except OSError:
            pass


@pytest.fixture
async def model_id(test_db) -> int:
    model = await get_model_by_name("ThinkPad T480")
    assert model is not None
    return model["model_id"]


@pytest.mark.asyncio
class TestUsers:
    async def test_register_user_idempotent(self, test_db):
        await register_user(42)
        await register_user(42)

        db = await get_db()
        async with db.execute("SELECT COUNT(*) FROM users WHERE user_id = 42") as cur:
            assert (await cur.fetchone())[0] == 1

    async def test_default_city_is_russia(self, test_db):
        await register_user(42)
        assert await get_cities(42) == ["Россия"]

    async def test_set_and_get_cities(self, test_db):
        await register_user(42)
        await set_cities(42, ["Москва", "Санкт-Петербург"])
        assert await get_cities(42) == ["Москва", "Санкт-Петербург"]

    async def test_init_db_creates_parent_directory(self, tmp_path):
        await close_db()
        original = database.DB_PATH
        database.DB_PATH = str(tmp_path / "nested" / "echelon.db")
        database._db = None

        try:
            await init_db()
            assert Path(database.DB_PATH).exists()
        finally:
            await close_db()
            database.DB_PATH = original
            database._db = None


@pytest.mark.asyncio
class TestModels:
    async def test_predefined_models_loaded(self, test_db):
        models = await get_all_models()
        names = {m["name"] for m in models}
        assert {"ThinkPad T480", "RTX 3060 Ti", "MikroTik hAP ac²"} <= names

    async def test_keywords_are_lists_not_strings(self, test_db):
        """JSON-сериализация: keywords должны прийти списком, не строкой."""
        model = await get_model_by_name("ThinkPad T480")
        assert isinstance(model["keywords"], list)
        assert all(isinstance(k, str) for k in model["keywords"])

    async def test_get_model_by_id(self, test_db, model_id):
        model = await get_model_by_id(model_id)
        assert model is not None
        assert model["name"] == "ThinkPad T480"

    async def test_toggle_user_model(self, test_db, model_id):
        await register_user(42)

        assert await toggle_user_model(42, model_id) is True
        assert [m["model_id"] for m in await get_user_models(42)] == [model_id]

        assert await toggle_user_model(42, model_id) is False
        assert await get_user_models(42) == []

    async def test_clear_user_models(self, test_db):
        await register_user(42)
        for model in await get_all_models():
            await toggle_user_model(42, model["model_id"])

        await clear_user_models(42)
        assert await get_user_models(42) == []

    async def test_active_users_includes_only_those_with_models(self, test_db, model_id):
        await register_user(1)
        await register_user(2)
        await toggle_user_model(1, model_id)

        users = await get_active_users_with_models()
        ids = {u["user_id"] for u in users}
        assert ids == {1}


@pytest.mark.asyncio
class TestListings:
    async def test_save_listings_skips_without_model_id(self, test_db, model_id):
        new_count = await save_listings(
            [
                {
                    "id": "a",
                    "url": "https://avito.ru/a",
                    "title": "T480 EUR",
                    "price": 20000,
                    "model_id": model_id,
                    "city": "Москва",
                },
                {
                    "id": "b",
                    "url": "https://avito.ru/b",
                    "title": "Без модели",
                    "price": 1000,
                    "city": "Москва",
                },
            ]
        )
        assert new_count == 1

    async def test_save_listings_dedup(self, test_db, model_id):
        listing = {
            "id": "a",
            "url": "https://avito.ru/a",
            "title": "T480",
            "price": 20000,
            "model_id": model_id,
            "city": "Москва",
        }
        assert await save_listings([listing]) == 1
        assert await save_listings([listing]) == 0

    async def test_discount_calculated_against_median(self, test_db, model_id):
        model = await get_model_by_id(model_id)
        median = model["median_price"]
        target_price = int(median * 0.8)

        await save_listings(
            [
                {
                    "id": "discounted",
                    "url": "https://avito.ru/x",
                    "title": "T480",
                    "price": target_price,
                    "model_id": model_id,
                    "city": "Москва",
                }
            ]
        )

        db = await get_db()
        async with db.execute(
            "SELECT discount_percent FROM listings WHERE listing_id = ?", ("discounted",)
        ) as cur:
            assert (await cur.fetchone())["discount_percent"] == 20

    async def test_new_listings_filter_by_threshold(self, test_db, model_id):
        await register_user(42)
        await toggle_user_model(42, model_id)

        model = await get_model_by_id(model_id)
        deep_discount = int(model["median_price"] * (1 - (model["discount_threshold"] + 5) / 100))
        shallow_discount = int(model["median_price"] * 0.99)

        await save_listings(
            [
                {
                    "id": "good",
                    "url": "https://avito.ru/good",
                    "title": "T480",
                    "price": deep_discount,
                    "model_id": model_id,
                    "city": "Москва",
                },
                {
                    "id": "bad",
                    "url": "https://avito.ru/bad",
                    "title": "T480",
                    "price": shallow_discount,
                    "model_id": model_id,
                    "city": "Москва",
                },
            ]
        )

        listings = await get_new_listings_for_user(42)
        assert [item["listing_id"] for item in listings] == ["good"]

    async def test_mark_sent_excludes_listing(self, test_db, model_id):
        await register_user(42)
        await toggle_user_model(42, model_id)

        model = await get_model_by_id(model_id)
        cheap = int(model["median_price"] * 0.5)
        await save_listings(
            [
                {
                    "id": "abc",
                    "url": "https://avito.ru/abc",
                    "title": "T480",
                    "price": cheap,
                    "model_id": model_id,
                    "city": "Москва",
                },
            ]
        )

        assert len(await get_new_listings_for_user(42)) == 1
        await mark_listing_sent(42, "abc")
        assert await get_new_listings_for_user(42) == []

    async def test_hidden_listing_is_excluded(self, test_db, model_id):
        await register_user(42)
        await toggle_user_model(42, model_id)

        model = await get_model_by_id(model_id)
        cheap = int(model["median_price"] * 0.5)
        await save_listings(
            [
                {
                    "id": "abc",
                    "url": "https://avito.ru/abc",
                    "title": "T480",
                    "price": cheap,
                    "model_id": model_id,
                    "city": "Москва",
                },
            ]
        )

        await hide_listing(42, "abc")
        assert await get_new_listings_for_user(42) == []

    async def test_city_filter(self, test_db, model_id):
        await register_user(42)
        await toggle_user_model(42, model_id)
        await set_cities(42, ["Москва"])

        model = await get_model_by_id(model_id)
        cheap = int(model["median_price"] * 0.5)
        await save_listings(
            [
                {
                    "id": "msk",
                    "url": "https://avito.ru/1",
                    "title": "T480",
                    "price": cheap,
                    "model_id": model_id,
                    "city": "Москва",
                },
                {
                    "id": "spb",
                    "url": "https://avito.ru/2",
                    "title": "T480",
                    "price": cheap,
                    "model_id": model_id,
                    "city": "Санкт-Петербург",
                },
            ]
        )

        ids = {item["listing_id"] for item in await get_new_listings_for_user(42)}
        assert ids == {"msk"}


@pytest.mark.asyncio
class TestFavorites:
    async def test_add_remove_favorite(self, test_db, model_id):
        await register_user(42)
        await save_listings(
            [
                {
                    "id": "fav1",
                    "url": "https://avito.ru/fav1",
                    "title": "T480",
                    "price": 20000,
                    "model_id": model_id,
                    "city": "Москва",
                }
            ]
        )

        await add_favorite(42, "fav1")
        assert await is_favorite(42, "fav1") is True

        favs = await get_favorites(42)
        assert len(favs) == 1
        assert favs[0]["model_name"] == "ThinkPad T480"

        await remove_favorite(42, "fav1")
        assert await is_favorite(42, "fav1") is False


@pytest.mark.asyncio
class TestMedian:
    async def test_returns_none_when_not_enough_data(self, test_db, model_id):
        for i in range(3):
            await save_listings(
                [
                    {
                        "id": f"x{i}",
                        "url": f"https://avito.ru/x{i}",
                        "title": "T480",
                        "price": 20000,
                        "model_id": model_id,
                        "city": "Москва",
                    }
                ]
            )

        assert await calculate_median_for_model(model_id) is None

    async def test_calculates_median_with_enough_data(self, test_db, model_id):
        prices = [10000 + i * 1000 for i in range(11)]
        listings = [
            {
                "id": f"x{i}",
                "url": f"https://avito.ru/x{i}",
                "title": "T480",
                "price": p,
                "model_id": model_id,
                "city": "Москва",
            }
            for i, p in enumerate(prices)
        ]
        await save_listings(listings)

        median = await calculate_median_for_model(model_id)
        assert median == 15000

    async def test_update_model_median(self, test_db, model_id):
        await update_model_median(model_id, 99999)
        model = await get_model_by_id(model_id)
        assert model["median_price"] == 99999


@pytest.mark.asyncio
class TestArchiving:
    async def test_cleanup_archives_to_price_history(self, test_db, model_id):
        from database import cleanup_listings, get_db

        db = await get_db()
        await db.execute(
            """INSERT INTO listings (listing_id, url, title, price, model_id, city, parsed_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now', '-31 days'))""",
            ("old_one", "http://x", "Old", 10000, model_id, "Москва"),
        )
        await db.commit()

        deleted = await cleanup_listings(30)
        assert deleted == 1

        async with db.execute(
            "SELECT price FROM price_history WHERE model_id = ?", (model_id,)
        ) as cur:
            row = await cur.fetchone()
            assert row is not None
            assert row[0] == 10000


@pytest.mark.asyncio
class TestAnalytics:
    async def test_total_savings_calculation(self, test_db, model_id):
        from database import get_stats, log_notification, register_user

        await register_user(42)

        await log_notification(42, "item1", "Model X", 15000, 20000, 25)

        stats = await get_stats()
        assert stats["total_savings"] == 5000

    async def test_get_price_history_combined(self, test_db, model_id):
        from database import get_db, get_price_history

        db = await get_db()

        await db.execute(
            "INSERT INTO price_history (model_id, price, city, recorded_at) VALUES (?, ?, ?, datetime('now', '-5 days'))",
            (model_id, 100, "Мск"),
        )

        await db.execute(
            """INSERT INTO listings (listing_id, url, title, price, model_id, city, parsed_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
            ("now1", "http://y", "Now", 200, model_id, "Мск"),
        )
        await db.commit()

        history = await get_price_history(model_id, days=10)
        assert len(history) == 2
        prices = [h["price"] for h in history]
        assert 100 in prices
        assert 200 in prices
