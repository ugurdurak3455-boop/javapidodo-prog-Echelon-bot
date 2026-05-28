# Предустановленные настройки моделей для отслеживания

from typing import Any

PREDEFINED_MODELS: list[dict[str, Any]] = [
    {
        "name": "ThinkPad T480",
        "category": "Ноутбуки",
        "keywords": ["t480", "thinkpad t480"],
        "stop_words": ["broken"],
        "price_min": 15000,
        "price_max": 35000,
        "initial_median": 25000,
        "discount_threshold": 15,
        "avito_search_url": "https://www.avito.ru/rossiya/noutbuki?q=thinkpad+t480",
    },
    {
        "name": "RTX 3060 Ti",
        "category": "Видеокарты",
        "keywords": ["3060 ti", "rtx 3060 ti"],
        "stop_words": ["broken", "нерабочая"],
        "price_min": 18000,
        "price_max": 30000,
        "initial_median": 24000,
        "discount_threshold": 10,
        "avito_search_url": "https://www.avito.ru/rossiya/tovary_dlya_kompyutera/komplektuyuschie/videokarty?q=rtx+3060+ti",
    },
    {
        "name": "MikroTik hAP ac²",
        "category": "Сетевое оборудование",
        "keywords": ["mikrotik hap ac2", "hap ac2"],
        "stop_words": ["сгорел", "нерабочий"],
        "price_min": 3000,
        "price_max": 7000,
        "initial_median": 5000,
        "discount_threshold": 15,
        "avito_search_url": "https://www.avito.ru/rossiya/tovary_dlya_kompyutera/setevoe_oborudovanie?q=mikrotik+hap+ac2",
    },
    {
        "name": "iPhone 16 Pro 128GB",
        "category": "Телефоны",
        "keywords": ["iphone 16 pro", "16 pro 128", "16 про 128"],
        "stop_words": [
            "r-sim",
            "bypass",
            "блокировка",
            "icloud",
            "запчасти",
            "разбит",
            "копия",
            "реф",
            "обмен",
            "mdm",
            "демо",
        ],
        "price_min": 55000,
        "price_max": 85000,
        "initial_median": 75000,
        "discount_threshold": 12,
        "avito_search_url": "https://www.avito.ru/rossiya/telefony?q=iphone+16+pro+128",
    },
    {
        "name": "MacBook Air M3 8/256",
        "category": "Ноутбуки",
        "keywords": ["macbook air m3", "m3 8gb", "m3 256"],
        "stop_words": [
            "icloud",
            "mdm",
            "bypass",
            "блокировка",
            "запчасти",
            "разбит экран",
            "коробка",
            "только чехол",
        ],
        "price_min": 70000,
        "price_max": 105000,
        "initial_median": 95000,
        "discount_threshold": 12,
        "avito_search_url": "https://www.avito.ru/rossiya/noutbuki?q=macbook+air+m3",
    },
    {
        "name": "Samsung Galaxy S26 Ultra",
        "category": "Телефоны",
        "keywords": ["s26 ultra", "galaxy s26 ultra", "samsung s26 ultra"],
        "stop_words": [
            "копия",
            "реплика",
            "корейская копия",
            "демо",
            "demo",
            "на запчасти",
            "разбит дисплей",
            "подделка",
        ],
        "price_min": 60000,
        "price_max": 110000,
        "initial_median": 90000,
        "discount_threshold": 15,
        "avito_search_url": "https://www.avito.ru/rossiya/telefony?q=s26+ultra",
    },
    {
        "name": "RTX 5060 8GB",
        "category": "Видеокарты",
        "keywords": ["rtx 5060", "nvidia 5060", "rtx5060"],
        "stop_words": [
            "коробка",
            "кулер",
            "нерабочая",
            "артефакты",
            "прогрев",
            "ноутбук",
            "системный блок",
            "пк",
            "только кулер",
        ],
        "price_min": 25000,
        "price_max": 40000,
        "initial_median": 34000,
        "discount_threshold": 15,
        "avito_search_url": "https://www.avito.ru/rossiya/tovary_dlya_kompyutera/komplektuyuschie/videokarty?q=rtx+5060",
    },
    {
        "name": "Ryzen 7 9800X3D",
        "category": "Процессоры",
        "keywords": ["9800x3d", "ryzen 9800x3d", "r7 9800x3d"],
        "stop_words": [
            "ножки",
            "погнуты",
            "неисправен",
            "сгорел",
            "7800x3d",
            "5800x3d",
            "кулер",
            "коробка от",
        ],
        "price_min": 30000,
        "price_max": 48000,
        "initial_median": 42000,
        "discount_threshold": 12,
        "avito_search_url": "https://www.avito.ru/rossiya/tovary_dlya_kompyutera/komplektuyuschie/protsessory?q=9800x3d",
    },
    {
        "name": "Steam Deck OLED 512GB",
        "category": "Игровые приставки",
        "keywords": ["steam deck oled", "стим дек oled", "deck oled 512"],
        "stop_words": [
            "чехол",
            "стекло",
            "lcd",
            "64gb",
            "аккаунт",
            "запчасти",
            "не включается",
            "винил",
            "корпус",
        ],
        "price_min": 35000,
        "price_max": 60000,
        "initial_median": 52000,
        "discount_threshold": 15,
        "avito_search_url": "https://www.avito.ru/rossiya/igry_pristavki_i_programmy/igrovye_pristavki?q=steam+deck+oled+512",
    },
    {
        "name": "MikroTik hAP ax3",
        "category": "Сетевое оборудование",
        "keywords": ["mikrotik hap ax3", "hap ax3", "c53uig+5hpaxd2hpaxd"],
        "stop_words": [
            "коробка",
            "блок питания",
            "нерабочий",
            "запчасти",
            "ax2",
            "ac2",
            "сгорел",
            "на запчасти",
        ],
        "price_min": 6000,
        "price_max": 13000,
        "initial_median": 10500,
        "discount_threshold": 20,
        "avito_search_url": "https://www.avito.ru/rossiya/tovary_dlya_kompyutera/setevoe_oborudovanie?q=mikrotik+hap+ax3",
    },
]


GLOBAL_STOP_WORDS: list[str] = [
    "обмен",
    "только обмен",
    "не продаю",
    "нет в наличии",
    "предзаказ",
    "под заказ",
]


def get_model_by_name(name: str) -> dict[str, Any] | None:
    """Получить конфигурацию модели по имени."""
    for model in PREDEFINED_MODELS:
        if model["name"].lower() == name.lower():
            return model
    return None


def get_all_model_names() -> list[str]:
    """Получить список всех доступных моделей."""
    return [model["name"] for model in PREDEFINED_MODELS]


def get_models_by_category(category: str) -> list[dict[str, Any]]:
    """Получить все модели определенной категории."""
    return [m for m in PREDEFINED_MODELS if m["category"] == category]
