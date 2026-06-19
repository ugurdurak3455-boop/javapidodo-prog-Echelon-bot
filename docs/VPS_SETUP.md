# Деплой на VPS

Avito склонен блокировать запросы из дата-центров. Минимальный набор
мер, чтобы продержаться без прокси:

- VPS в Европе (российские дата-центры блокируются заметно агрессивнее).
- `UPDATE_INTERVAL_FREE` ≥ 120 минут.
- Не запускать несколько ботов с одного IP.

## Установка

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2

git clone <repo-url> echelon
cd echelon
python3 -m venv .venv
source .venv/bin/activate
pip install uv
uv pip install -r requirements.txt
playwright install chromium
```

## Конфиг

```bash
cp .env.example .env
nano .env  # заполнить BOT_TOKEN и ADMIN_USER_ID
```

## Запуск через systemd

`/etc/systemd/system/echelon.service`:

```ini
[Unit]
Description=Echelon Telegram Bot
After=network.target

[Service]
Type=simple
User=USERNAME
WorkingDirectory=/home/USERNAME/echelon
Environment="PATH=/home/USERNAME/echelon/.venv/bin"
ExecStart=/home/USERNAME/echelon/.venv/bin/python bot.py

Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now echelon
sudo systemctl status echelon
sudo journalctl -u echelon -f
```

## Мониторинг

```bash
tail -f bot.log                  # логи бота
grep -E "ERROR|Blocked|CAPTCHA" bot.log
```

В логах после каждого цикла парсинга должна быть строка вида
`Parser: saved N new listings (M parsed)`. Если `M` стабильно равен
нулю — Avito блокирует или поменялась вёрстка.

## Если блокирует

1. Поднять `UPDATE_INTERVAL_FREE` в `config.py` до 180–240 минут и
   перезапустить сервис.
2. Парсить только в нерабочие часы — добавить проверку времени в
   `tasks.parser_task` перед вызовом `scraper.run`:

   ```python
   from datetime import datetime
   if 9 <= datetime.now().hour < 23:
       await asyncio.sleep(900)
       continue
   ```

3. Ротировать модели по дням недели — внутри `get_models_to_parse`
   фильтровать модели по `datetime.now().weekday()`.
