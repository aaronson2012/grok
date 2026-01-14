"""
Centralized permission utilities for both Discord and Telegram.
"""
from functools import wraps
from ..config import config


def is_telegram_admin(user_id: int) -> bool:
    """Check if a Telegram user is an admin."""
    return user_id in config.TELEGRAM_ADMIN_IDS


def require_telegram_admin(func):
    """Decorator that requires Telegram admin permissions."""
    @wraps(func)
    async def wrapper(update, context):
        if not is_telegram_admin(update.effective_user.id):
            await update.message.reply_text("❌ This command requires admin permissions.")
            return
        return await func(update, context)
    return wrapper
