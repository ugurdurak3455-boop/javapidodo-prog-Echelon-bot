# Конфиг приложения Echelon

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(Path(__file__).parent / ".env"), extra="ignore")

    BOT_TOKEN: str
    ADMIN_ID: int = Field(default=0, alias="ADMIN_USER_ID")
    DB_PATH: str = Field(default="storage/db/echelon.db", validation_alias="DB_NAME")

    DASHBOARD_HOST: str = Field(default="127.0.0.1", alias="ADMIN_DASHBOARD_HOST")
    DASHBOARD_PORT: int = Field(default=8080, alias="ADMIN_DASHBOARD_PORT")
    DASHBOARD_USER: str = ""
    DASHBOARD_PASS: str = ""

    MODE: str = Field(default="demo", alias="SCRAPER_MODE")
    HEADLESS: bool = Field(default=True, alias="SCRAPER_HEADLESS")
    SCRAPER_TYPE: str = Field(default="curl_cffi", alias="SCRAPER_TYPE")

    FREE_LIMITS: dict[str, int] = {"models": 3, "cities": 1}
    PREMIUM_LIMITS: dict[str, int] = {"models": 7, "cities": 3}

    MAX_JOBS: int = Field(default=50, alias="PARSER_MAX_JOBS_PER_CYCLE")
    INTERVAL_FREE: int = 5
    INTERVAL_PREMIUM: int = 1

    RETENTION_DAYS: int = 30
    INACTIVE_DAYS: int = 180

    PROXY_URL: str = ""
    PROXIES: list[str] = Field(default_factory=list, alias="PROXY_LIST")
    USER_DATA_DIR: str = str(Path(__file__).parent / "storage" / "browser")

    CITIES: list[str] = [
        "Россия",
        "Москва",
        "Санкт-Петербург",
        "Новосибирск",
        "Екатеринбург",
        "Казань",
        "Нижний Новгород",
        "Челябинск",
        "Самара",
        "Омск",
        "Ростов-на-Дону",
        "Уфа",
        "Красноярск",
        "Воронеж",
        "Пермь",
        "Волгоград",
        "Краснодар",
        "Саратов",
        "Тюмень",
        "Тольятти",
    ]

    CITY_SLUGS: dict[str, str] = {
        "Россия": "rossiya",
        "Москва": "moskva",
        "Санкт-Петербург": "sankt-peterburg",
        "Новосибирск": "novosibirsk",
        "Екатеринбург": "ekaterinburg",
        "Казань": "kazan",
        "Нижний Новгород": "nizhniy_novgorod",
        "Челябинск": "chelyabinsk",
        "Самара": "samara",
        "Омск": "omsk",
        "Ростов-на-Дону": "rostov-na-donu",
        "Уфа": "ufa",
        "Красноярск": "krasnoyarsk",
        "Воронеж": "voronezh",
        "Пермь": "perm",
        "Волгоград": "volgograd",
        "Краснодар": "krasnodar",
        "Саратов": "saratov",
        "Тюмень": "tyumen",
        "Тольятти": "tolyatti",
    }

    CITIES_PER_PAGE: int = 5
    BYPASS_DELAY: bool = True


settings = Settings()  # type: ignore[call-arg]
