"""Тесты utils/keyboards.py."""

import pytest

from utils.keyboards import (
    ActionCB,
    CityCB,
    CityPageCB,
    FavoriteCB,
    ListingNavCB,
    ModelCB,
    NotificationCB,
    get_city_keyboard,
    get_models_keyboard,
)


def _texts(keyboard) -> list[str]:
    return [btn.text for row in keyboard.inline_keyboard for btn in row]


class TestCallbackData:
    def test_model_cb_round_trip(self):
        packed = ModelCB(action="toggle", model_id=7).pack()
        assert ModelCB.unpack(packed) == ModelCB(action="toggle", model_id=7)

    def test_action_cb_round_trip(self):
        packed = ActionCB(action="finish_models").pack()
        assert ActionCB.unpack(packed) == ActionCB(action="finish_models")

    def test_city_cb_round_trip(self):
        packed = CityCB(name="Москва").pack()
        assert CityCB.unpack(packed) == CityCB(name="Москва")

    def test_city_page_cb_round_trip(self):
        packed = CityPageCB(page=2).pack()
        assert CityPageCB.unpack(packed) == CityPageCB(page=2)

    def test_favorite_cb_round_trip(self):
        packed = FavoriteCB(action="add", listing_id="abc123").pack()
        assert FavoriteCB.unpack(packed) == FavoriteCB(action="add", listing_id="abc123")

    def test_notification_cb_round_trip(self):
        packed = NotificationCB(action="show", model_name="RTX 3060 Ti").pack()
        assert NotificationCB.unpack(packed) == NotificationCB(
            action="show", model_name="RTX 3060 Ti"
        )

    def test_listing_nav_cb_round_trip(self):
        packed = ListingNavCB(action="next", model_name="T480", index=3).pack()
        assert ListingNavCB.unpack(packed) == ListingNavCB(
            action="next", model_name="T480", index=3
        )


class TestModelsKeyboard:
    @pytest.fixture
    def models(self):
        return [
            {
                "model_id": 1,
                "name": "ThinkPad T480",
                "category": "Ноутбуки",
                "price_min": 15000,
                "price_max": 35000,
                "discount_threshold": 15,
            },
            {
                "model_id": 2,
                "name": "RTX 3060 Ti",
                "category": "Видеокарты",
                "price_min": 18000,
                "price_max": 30000,
                "discount_threshold": 10,
            },
        ]

    def test_renders_all_models(self, models):
        keyboard = get_models_keyboard([], models)
        texts = _texts(keyboard)
        for model in models:
            assert any(model["name"] in t for t in texts)

    def test_marks_selected_with_checkmark(self, models):
        texts = _texts(get_models_keyboard([1], models))
        assert any("✅" in t and "ThinkPad" in t for t in texts)
        assert not any("✅" in t and "RTX" in t for t in texts)

    def test_clear_button_only_with_selection(self, models):
        empty = _texts(get_models_keyboard([], models))
        assert not any("Очистить" in t for t in empty)

        with_sel = _texts(get_models_keyboard([1], models))
        assert any("Очистить" in t for t in with_sel)

    def test_finish_button_always_present(self, models):
        for selected in ([], [1]):
            assert any("Готово" in t for t in _texts(get_models_keyboard(selected, models)))


class TestCityKeyboard:
    CITIES = ["Россия", "Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань"]

    def test_marks_selected_with_checkmark(self):
        texts = _texts(get_city_keyboard(["Москва"], self.CITIES, 5, page=0))
        assert any("✅" in t and "Москва" in t for t in texts)

    def test_no_back_button_on_first_page(self):
        texts = _texts(get_city_keyboard([], self.CITIES, 3, page=0))
        assert not any("Назад" in t for t in texts)

    def test_back_button_on_later_pages(self):
        texts = _texts(get_city_keyboard([], self.CITIES, 3, page=1))
        assert any("Назад" in t for t in texts)

    def test_no_forward_button_on_last_page(self):
        texts = _texts(get_city_keyboard([], self.CITIES, 3, page=1))
        assert not any("Вперед" in t for t in texts)

    def test_pagination_respects_page_size(self):
        keyboard = get_city_keyboard([], self.CITIES, 3, page=0)
        nav_words = ("Готово", "📥", "Назад", "Вперед", "◀️", "▶️")
        city_buttons = [
            btn
            for row in keyboard.inline_keyboard
            for btn in row
            if not any(word in btn.text for word in nav_words)
        ]
        assert len(city_buttons) == 3

    def test_finish_button_present(self):
        assert any("Готово" in t for t in _texts(get_city_keyboard([], self.CITIES, 5, page=0)))
