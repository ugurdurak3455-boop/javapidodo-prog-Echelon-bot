from .admin import router as admin_router
from .callbacks import router as callbacks_router
from .commands import router as commands_router

__all__ = ["commands_router", "callbacks_router", "admin_router"]
