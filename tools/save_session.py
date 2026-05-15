"""
tools/save_session.py — утилита для ручного прохождения капчи и сохранения сессии.
Запустите этот скрипт, пройдите капчу в открывшемся окне браузера и нажмите Enter в консоли.
"""

import asyncio
import os
import sys

from playwright.async_api import async_playwright

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import settings


async def save_session():
    user_data_dir = settings.USER_DATA_DIR

    print(f"\nИнициализация чистого профиля в: {user_data_dir}")


    async with async_playwright() as p:
        # Запускаем чистый стандартный браузер без маскировки и кастомных профилей
        browser = await p.chromium.launch(
            headless=False,
            args=["--start-maximized"],
        )
        context = await browser.new_context(
            viewport=None, # Для корректной работы максимизации
        )

        page = await context.new_page()

        print("\nОткрываем Avito...")
        try:
            await page.goto("https://www.avito.ru", wait_until="commit", timeout=60000)
        except Exception as e:
            print(f"Загрузка страницы: {e}")

        print("\n" + "=" * 60)
        print("ДЕЙСТВИЯ:")
        print("1. Пройдите капчу.")
        print("2. Войдите в аккаунт (желательно).")
        print("3. Пооткрывайте объявления, убедитесь что всё грузится.")
        print("4. Нажмите ENTER в этой консоли.")
        print("=" * 60 + "\n")

        await asyncio.to_thread(input, "Нажмите Enter для сохранения и выхода...")

        try:
            # Экспортируем куки и User-Agent из контекста
            cookies = await context.cookies()
            user_agent = await page.evaluate("navigator.userAgent")

            project_root = os.path.dirname(os.path.dirname(__file__))
            storage_dir = os.path.join(project_root, "storage")
            os.makedirs(storage_dir, exist_ok=True)

            cookies_path = os.path.join(storage_dir, "cookies.json")
            ua_path = os.path.join(storage_dir, "user_agent.txt")

            import json

            with open(cookies_path, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=4, ensure_ascii=False)
            print(f"[OK] Куки успешно экспортированы в {cookies_path}")

            with open(ua_path, "w", encoding="utf-8") as f:
                f.write(user_agent)
            print(f"[OK] User-Agent сохранен в {ua_path}")

            await context.close()
        except Exception as e:
            print(f"Ошибка при закрытии браузера или сохранении кук: {e}")

        print("\n[OK] Сессия сохранена. Теперь можно запускать бота.")


if __name__ == "__main__":
    try:
        asyncio.run(save_session())
    except Exception as e:
        print(f"\n[ERR] Критическая ошибка при запуске: {e}")
        import traceback

        traceback.print_exc()
        input("\nНажмите Enter, чтобы закрыть окно...")
