from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message, TelegramObject, Update, User

import database
from utils.middleware import AutoRegisterMiddleware


@pytest.mark.asyncio
async def test_middleware_registers_user_from_data(monkeypatch):
    middleware = AutoRegisterMiddleware()

    mock_register = AsyncMock()
    mock_set_active = AsyncMock()
    monkeypatch.setattr(database, "register_user", mock_register)
    monkeypatch.setattr(database, "set_user_active", mock_set_active)

    event = MagicMock(spec=TelegramObject)

    user = MagicMock(spec=User)
    user.id = 12345
    data = {"event_from_user": user}

    handler = AsyncMock(return_value="handler_response")

    res = await middleware(handler, event, data)

    assert res == "handler_response"
    mock_register.assert_called_once_with(12345)
    mock_set_active.assert_called_once_with(12345, True)
    handler.assert_called_once_with(event, data)


@pytest.mark.asyncio
async def test_middleware_registers_user_from_nested_event(monkeypatch):
    middleware = AutoRegisterMiddleware()

    mock_register = AsyncMock()
    mock_set_active = AsyncMock()
    monkeypatch.setattr(database, "register_user", mock_register)
    monkeypatch.setattr(database, "set_user_active", mock_set_active)

    mock_update = MagicMock(spec=Update)
    mock_message = MagicMock(spec=Message)
    mock_user = MagicMock(spec=User)
    mock_user.id = 67890
    mock_message.from_user = mock_user
    mock_update.event = mock_message

    data: dict = {}
    handler = AsyncMock(return_value="response")

    res = await middleware(handler, mock_update, data)

    assert res == "response"
    mock_register.assert_called_once_with(67890)
    mock_set_active.assert_called_once_with(67890, True)
    handler.assert_called_once_with(mock_update, data)


@pytest.mark.asyncio
async def test_middleware_handles_no_user_gracefully(monkeypatch):
    middleware = AutoRegisterMiddleware()

    mock_register = AsyncMock()
    mock_set_active = AsyncMock()
    monkeypatch.setattr(database, "register_user", mock_register)
    monkeypatch.setattr(database, "set_user_active", mock_set_active)

    event = MagicMock(spec=TelegramObject)
    event.event = MagicMock()
    del event.event.from_user
    del event.from_user

    data: dict = {}
    handler = AsyncMock(return_value="ok")

    res = await middleware(handler, event, data)

    assert res == "ok"
    mock_register.assert_not_called()
    mock_set_active.assert_not_called()
    handler.assert_called_once_with(event, data)
