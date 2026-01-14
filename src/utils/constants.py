"""
Platform-specific constants and limits.
"""
from enum import Enum


class Platform(Enum):
    DISCORD = "discord"
    TELEGRAM = "telegram"


# Message character limits
DISCORD_MESSAGE_LIMIT = 2000
DISCORD_RESPONSE_LIMIT = 1900  # Leave buffer for formatting
TELEGRAM_MESSAGE_LIMIT = 4096
TELEGRAM_RESPONSE_LIMIT = 3900  # Leave buffer for formatting

# Chunk sizes for splitting long messages
DISCORD_CHUNK_SIZE = 1900
TELEGRAM_CHUNK_SIZE = 3900

# Time constants (seconds)
CONTEXT_RESET_THRESHOLD = 86400  # 24 hours

# History limits
MAX_HISTORY_MESSAGES = 300

# Digest constants
DEFAULT_MAX_TOPICS = 10
MAX_TOPICS_LIMIT = 50

# Summarization threshold
SUMMARIZATION_THRESHOLD_DISCORD = 10
SUMMARIZATION_THRESHOLD_TELEGRAM = 2
