import json
import os
from datetime import UTC, datetime
from typing import Any, List, Dict

from pydantic import BaseModel, ConfigDict
import database as db
from config import settings
from models_config import GLOBAL_STOP_WORDS

class Price(BaseModel):
    value: int = 0

class Listing(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str | int
    urlPath: str
    title: str
    description: str | None = ""
    priceDetailed: Price | None = None
    sortTimeStamp: int | None = None
    image_url: str | None = None

class AvitoBlockedError(RuntimeWarning):
    pass

def _format_url(url: str, city: str) -> str:
    slug = settings.CITY_SLUGS.get(city, "rossiya")
    if "/rossiya/" in url:
        url = url.replace("/rossiya/", f"/{slug}/")
    elif slug != "rossiya":
        import re
        match = re.match(r"^(https?://[^/]+/)([^/?#]+)(.*)$", url)
        if match:
            base, cur, rest = match.groups()
            if cur != slug:
                url = f"{base}{slug}{rest}"

    if "s=104" not in url:
        url += ("&" if "?" in url else "?") + "s=104"
    return url

class DemoModelBasedScraper:
    async def run(self, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        import random
        listings = []
        for job in jobs:
            model = job["model"]
            if hasattr(model, "median_price"):
                median = model.median_price
                model_id = model.model_id
                price_min = model.price_min
                threshold = model.discount_threshold
                name = model.name
            else:
                median = model.get("median_price", 0)
                model_id = model.get("model_id", 0)
                price_min = model.get("price_min", 0)
                threshold = model.get("discount_threshold", 0)
                name = model.get("name", "")

            discount = threshold + 5
            good_price = max(price_min, int(median * (1 - discount / 100)))
            listings.append(
                {
                    "id": str(random.randint(100000000, 999999999)),
                    "model_id": model_id,
                    "model_name": name,
                    "city": job["city"],
                    "price": good_price,
                    "url": "https://avito.ru/demo",
                    "title": "Demo listing",
                    "discount_percent": discount,
                }
            )
        return listings

async def build_jobs_for_users(users: list[db.User]) -> list[dict[str, Any]]:
    jobs = []
    seen = set()
    for user in users:
        models = await db.get_user_models(user.user_id)
        cities = await db.get_cities(user.user_id)
        for m in models:
            for c in cities:
                if (m.model_id, c) not in seen:
                    jobs.append({"model": m, "city": c})
                    seen.add((m.model_id, c))
    return jobs

async def get_models_to_parse() -> list[dict[str, Any]]:
    users = await db.get_users_due_for_scan()
    return await build_jobs_for_users(users)

import asyncio
import random
import re
import logging
from typing import List, Dict, Optional

from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeoutError
from fake_useragent import UserAgent

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class AvitoScraper:
    """Асинхронный отказоустойчивый парсер для сайтов объявлений."""
    def __init__(self, headless: bool = None):
        self.headless = settings.HEADLESS if headless is None else headless
        self.ua = UserAgent(os='windows', browsers=['chrome', 'edge', 'firefox'])


    async def _random_scroll(self, page: Page):
        """Anti-Detection: Имитация чтения страницы пользователем."""
        scroll_steps = random.randint(3, 7)
        for _ in range(scroll_steps):
            scroll_y = random.randint(300, 700)
            await page.mouse.wheel(0, scroll_y)
            await asyncio.sleep(random.uniform(0.5, 1.5))
        
        await page.mouse.wheel(0, -random.randint(100, 300))
        await asyncio.sleep(random.uniform(0.5, 1.2))


    def _clean_price(self, price_str: str) -> Optional[int]:
        """Очистка строки с ценой и приведение к целому числу."""
        if not price_str or "бесплатно" in price_str.lower():
            return 0
        cleaned = re.sub(r'[^\d]', '', price_str)
        return int(cleaned) if cleaned else None


    async def _check_for_blocks(self, page: Page):
        """Проверка на наличие CAPTCHA или IP-блокировки."""
        title = await page.title()
        title_lower = title.lower()
        if "докажите, что вы человек" in title_lower or "captcha" in title_lower or "ой!" in title_lower:
            logging.error("Обнаружена капча или блокировка по IP!")
            raise AvitoBlockedError("Blocked or CAPTCHA detected")


    async def parse_page(self, page: Page, url: str, city: str) -> List[Dict]:
        logging.info(f"Начинаю обработку категории '{city}': {url}")
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await self._check_for_blocks(page)
            item_selector = '[data-marker="item"]'
            try:
                await page.wait_for_selector(item_selector, timeout=15000)
            except PlaywrightTimeoutError:
                logging.error("Не удалось найти объявления на странице. Возможно, сменилась верстка или Авито заблокировал доступ.")
                
                # Сохраняем скриншот для дебага
                debug_dir = os.path.join(os.path.dirname(__file__), "storage", "debug")
                os.makedirs(debug_dir, exist_ok=True)
                screenshot_path = os.path.join(debug_dir, f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                await page.screenshot(path=screenshot_path)
                logging.info(f"Скриншот ошибки сохранен в {screenshot_path}")
                
                return []
            
            # Скроллим только когда контент точно загрузился и страница стала длинной
            await self._random_scroll(page)

            items = await page.query_selector_all(item_selector)
            results = []

            for item in items:
                try:
                    link_elem = await item.query_selector('a[itemprop="url"]')
                    if not link_elem:
                        link_elem = await item.query_selector('a') # Резерв: любая ссылка в карточке
                    
                    href = await link_elem.get_attribute('href') if link_elem else ""
                    full_url = f"https://www.avito.ru{href}" if href and not href.startswith('http') else href

                    title_elem = await item.query_selector('[data-marker="item-title"]')
                    if not title_elem:
                        title_elem = await item.query_selector('h3[itemprop="name"], h2[itemprop="name"], h3, h2')
                    title = await title_elem.inner_text() if title_elem else "Без названия"

                    snippet_elem = await item.query_selector('meta[itemprop="description"]')
                    if snippet_elem:
                        snippet = await snippet_elem.get_attribute("content") or ""
                    else:
                        snippet_elem = await item.query_selector('[class*="description"], [class*="body-text"]')
                        snippet = await snippet_elem.inner_text() if snippet_elem else ""
                    
                    price = 0
                    price_meta = await item.query_selector('meta[itemprop="price"]')
                    if price_meta:
                        price_str = await price_meta.get_attribute('content')
                        price = int(price_str) if price_str and price_str.isdigit() else 0
                    else:
                        price_elem = await item.query_selector('[class*="price"]')
                        price_str = await price_elem.inner_text() if price_elem else ""
                        price = self._clean_price(price_str)

                    item_id = await item.get_attribute('data-item-id')
                    if not item_id and href:
                        match = re.search(r'_(\d+)$', href)
                        item_id = match.group(1) if match else "Unknown"

                    final_id = int(item_id) if isinstance(item_id, str) and item_id.isdigit() else item_id

                    snippet_elem = await item.query_selector('[class*="description"], [class*="body-text"]')
                    snippet = await snippet_elem.inner_text() if snippet_elem else ""

                    if title == "Без названия" and price == 0 and not href:
                        continue

                    results.append({
                        "city": city,
                        "id": final_id,
                        "title": title.strip(),
                        "price": price,
                        "url": full_url,
                        "snippet": snippet.strip().replace('\n', ' | ')
                    })

                except Exception as e:
                    logging.warning(f"Ошибка при парсинге конкретного лота: {e}")
                    continue
            
            logging.info(f"Успешно собрано {len(results)} объявлений.")
            return results

        except AvitoBlockedError as e:
            raise e
        except Exception as e:
            logging.error(f"Критическая ошибка страницы: {e}")
            return []

    def _filter(self, items: list[Any], model: db.Model, city: str) -> list[dict]:
        valid = []
        for it in items:
            it_dict = it if isinstance(it, dict) else {}
            title = it_dict.get("title") or ""
            description = it_dict.get("snippet") or it_dict.get("description") or ""
            full = f"{title} {description}".lower()

            if not any(k.lower() in full for k in model.keywords):
                continue
            if any(s.lower() in full for s in (*model.stop_words, *GLOBAL_STOP_WORDS)):
                continue

            price = it_dict.get("price") or 0

            if not (model.price_min <= price <= model.price_max):
                continue

            item_id = it_dict.get("id")

            valid.append(
                {
                    "model_id": model.model_id,
                    "model_name": model.name,
                    "city": city,
                    "id": str(item_id),
                    "title": title,
                    "price": price,
                    "url": it_dict.get("url") or "",
                    "image_url": it_dict.get("image_url"),
                    "description_preview": description[:200],
                }
            )
        return valid

    def _apply_filters(self, items: list[Any], model: db.Model | dict, city: str) -> list[dict]:
        if isinstance(model, dict):
            model_data = {
                "model_id": model.get("model_id", 0),
                "name": model.get("name", ""),
                "city": model.get("city", ""),
                "keywords": model.get("keywords", []),
                "stop_words": model.get("stop_words", []),
                "price_min": model.get("price_min", 0),
                "price_max": model.get("price_max", 0),
                "median_price": model.get("median_price", 0),
                "discount_threshold": model.get("discount_threshold", 0),
                "last_median_update": datetime.now(),
            }
            model = db.Model.model_validate(model_data)
        return self._filter(items, model, city)

    async def run(self, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Точка входа: запуск браузера и проход по списку URL."""
        all_data = []
        
        async with async_playwright() as p:
            all_data = []
            
            launch_kwargs = {
                "headless": self.headless,
                "args": [
                    '--disable-blink-features=AutomationControlled',
                    '--disable-infobars',
                    '--no-sandbox',
                    '--disable-dev-shm-usage'
                ]
            }
            
            proxies = []
            if getattr(settings, 'PROXY_URL', ''):
                proxies.append(settings.PROXY_URL)
            if getattr(settings, 'PROXIES', []):
                proxies.extend(settings.PROXIES)
                
            if proxies:
                launch_kwargs["proxy"] = {"server": random.choice(proxies)}
                
            browser = await p.chromium.launch(**launch_kwargs)
            
            storage_dir = os.path.join(os.path.dirname(__file__), "storage")
            cookies_path = os.path.join(storage_dir, "cookies.json")
            ua_path = os.path.join(storage_dir, "user_agent.txt")
            
            user_agent = self.ua.random
            if os.path.exists(ua_path):
                with open(ua_path, "r", encoding="utf-8") as f:
                    user_agent = f.read().strip()
            
            context = await browser.new_context(
                user_agent=user_agent,
                viewport={'width': random.randint(1366, 1920), 'height': random.randint(768, 1080)}
            )
            
            if os.path.exists(cookies_path):
                import json
                try:
                    with open(cookies_path, "r", encoding="utf-8") as f:
                        cookies = json.load(f)
                    await context.add_cookies(cookies)
                    logging.info("🍪 Session cookies loaded from storage/cookies.json")
                except Exception as e:
                    logging.error(f"Failed to load cookies: {e}")
            
            page = await context.new_page()
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            await page.add_init_script("""
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
                Object.defineProperty(navigator, 'languages', {get: () => ['ru-RU', 'ru', 'en-US', 'en']});
                                       """)            

            for job in jobs:
                model = job["model"]
                city = job["city"]
                base_url = _format_url(
                    getattr(model, "search_url", None)
                    or getattr(model, "avito_search_url", None)
                    or "",
                    city,
                )
                if not base_url:
                    continue

                max_pages = 3
                for page_num in range(1, max_pages + 1):
                    if page_num == 1:
                        url = base_url
                    else:
                        sep = "&" if "?" in base_url else "?"
                        url = f"{base_url}{sep}p={page_num}"

                    raw_items = await self.parse_page(page, url, city)
                    if not raw_items:
                        break  # Не нашли вообще никаких объявлений на странице, дальше парсить нет смысла

                    filtered = self._apply_filters(raw_items, model, city)
                    all_data.extend(filtered)
                    
                    if filtered:
                        break  # Нашли подходящие объявления, на следующую страницу не идем
                        
                    if page_num < max_pages:
                        logging.info(f"Подходящих объявлений на стр. {page_num} нет. Идем на {page_num + 1}...")
                        await asyncio.sleep(random.uniform(2.0, 4.0))

                await asyncio.sleep(random.uniform(3.0, 6.0))

            await browser.close()
            
        return all_data


