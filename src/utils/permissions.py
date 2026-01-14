"""
Centralized permission utilities for both Discord and Telegram.
"""
from ..config import config


def is_telegram_admin(user_id: int) -> bool:
    """Check if a Telegram user is an admin."""
    return user_id in config.TELEGRAM_ADMIN_IDS
