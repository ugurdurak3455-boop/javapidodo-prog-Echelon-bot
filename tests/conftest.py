import pytest

from config import settings


@pytest.fixture(autouse=True)
def enable_bypass_delay():
    original = settings.BYPASS_DELAY
    settings.BYPASS_DELAY = True
    yield
    settings.BYPASS_DELAY = original
