.PHONY: install run-bot run-dashboard test lint format clean

PYTHON = .venv/Scripts/python
PIP = .venv/Scripts/pip
PYTEST = .venv/Scripts/pytest
RUFF = .venv/Scripts/ruff

install:
	$(PIP) install uv
	.venv/Scripts/uv pip install -r requirements.txt
	.venv/Scripts/uv pip install -e .[dev]
	.venv/Scripts/playwright install chromium

run-bot:
	$(PYTHON) bot.py

run-dashboard:
	$(PYTHON) admin_dashboard.py

test:
	$(PYTHON) -m pytest

lint:
	$(RUFF) check .

format:
	$(RUFF) format .

clean:
	@if exist .pytest_cache rmdir /s /q .pytest_cache
	@if exist .ruff_cache rmdir /s /q .ruff_cache
	@if exist .mypy_cache rmdir /s /q .mypy_cache
	@for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
