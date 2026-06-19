from unittest.mock import AsyncMock

import pytest
from aiogram.types import Message

from utils.helpers import error_handler


@pytest.mark.asyncio
async def test_error_handler_success():
    mock_func = AsyncMock(return_value="success")
    decorated = error_handler(mock_func)

    result = await decorated("some_event")
    assert result == "success"
    mock_func.assert_called_once()


@pytest.mark.asyncio
async def test_error_handler_exception():
    mock_func = AsyncMock(side_effect=Exception("Test error"))
    decorated = error_handler(mock_func)

    mock_message = AsyncMock(spec=Message)
    mock_message.from_user = AsyncMock()
    mock_message.from_user.id = 123
    mock_message.answer = AsyncMock()

    result = await decorated(mock_message)
    assert result is None
    mock_message.answer.assert_called_once_with("Произошла ошибка. Попробуйте позже.")
