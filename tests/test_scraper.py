"""Tests for scraper filtering and parse job planning."""

import pytest

import database
from database import (
    clear_user_models,
    close_db,
    get_all_models,
    init_db,
    init_models_from_config,
    register_user,
    set_cities,
    toggle_user_model,
)
from scraper import (
    AvitoScraper,
    DemoModelBasedScraper,
    Item,
    PriceDetailed,
    _search_url_for_city,
    get_models_to_parse,
)


@pytest.fixture
async def test_db(tmp_path):
    original = database.DB_PATH
    database.DB_PATH = str(tmp_path / "test.db")
    database._db = None

    await init_db()
    await init_models_from_config()

    try:
        yield
    finally:
        await close_db()
        database.DB_PATH = original
        database._db = None


class TestCitySearchUrl:
    def test_replaces_russia_segment_with_city_slug(self):
        url = "https://www.avito.ru/rossiya/noutbuki?q=thinkpad+t480"

        result = _search_url_for_city(url, "Москва")

        assert "moskva" in result
        assert "s=104" in result

    def test_keeps_url_for_unknown_city(self):
        url = "https://www.avito.ru/rossiya/noutbuki?q=thinkpad+t480"

        result = _search_url_for_city(url, "Unknown")

        assert "rossiya" in result


class TestModelBasedFilter:
    def test_keeps_only_matching_price_range_and_clean_titles(self):
        model = {
            "model_id": 10,
            "name": "ThinkPad T480",
            "keywords": ["t480", "thinkpad t480"],
            "stop_words": ["broken"],
            "price_min": 15_000,
            "price_max": 35_000,
        }

        raw = [
            Item(
                id="ok",
                title="Lenovo ThinkPad T480",
                priceDetailed=PriceDetailed(value=22_000),
                urlPath="/ok",
                description="good condition",
            ),
            Item(
                id="wrong-keyword",
                title="Lenovo ThinkPad X260",
                priceDetailed=PriceDetailed(value=20_000),
                urlPath="/wrong-keyword",
                description="good condition",
            ),
            Item(
                id="too-cheap",
                title="Lenovo ThinkPad T480",
                priceDetailed=PriceDetailed(value=5_000),
                urlPath="/too-cheap",
                description="good condition",
            ),
            Item(
                id="stop-word",
                title="Lenovo ThinkPad T480",
                priceDetailed=PriceDetailed(value=20_000),
                urlPath="/stop-word",
                description="broken keyboard",
            ),
            Item(
                id="global-stop-word",
                title="Lenovo ThinkPad T480 только обмен",
                priceDetailed=PriceDetailed(value=20_000),
                urlPath="/stop-word",
                description="good condition",
            ),
        ]

        scraper = AvitoScraper()
        result = scraper._apply_filters(raw, model, "Moscow")

        assert len(result) == 1
        assert result[0]["id"] == "ok"
        assert result[0]["model_name"] == "ThinkPad T480"
        assert result[0]["price"] == 22_000


@pytest.mark.asyncio
async def test_demo_scraper_generates_discounted_listings():
    model = {
        "model_id": 10,
        "name": "ThinkPad T480",
        "median_price": 24_500,
        "discount_threshold": 15,
        "price_min": 15_000,
    }
    jobs = [{"model": model, "city": "Moscow"}]

    listings = await DemoModelBasedScraper().run(jobs)

    assert len(listings) == 1
    assert listings[0]["model_id"] == 10
    assert listings[0]["city"] == "Moscow"

    assert listings[0]["price"] == 19600


@pytest.mark.asyncio
async def test_get_models_to_parse_deduplicates_model_city_pairs(test_db):
    models = await get_all_models()
    first_model_id = models[0]["model_id"]
    second_model_id = models[1]["model_id"]

    await register_user(1)
    await register_user(2)
    await register_user(3)

    await toggle_user_model(1, first_model_id)
    await toggle_user_model(2, first_model_id)
    await toggle_user_model(3, second_model_id)

    await set_cities(1, ["Moscow", "Saint Petersburg"])
    await set_cities(2, ["Moscow"])
    await set_cities(3, ["Moscow"])

    jobs = await get_models_to_parse()
    pairs = {(job["model"]["model_id"], job["city"]) for job in jobs}

    assert pairs == {
        (first_model_id, "Moscow"),
        (first_model_id, "Saint Petersburg"),
        (second_model_id, "Moscow"),
    }

    await clear_user_models(1)
    await clear_user_models(2)
    await clear_user_models(3)
