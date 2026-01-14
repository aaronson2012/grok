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
TELEGRAM_ADMIN_CONTENT_LIMIT = 3500  # Truncation limit for admin memory view

# Chunk sizes for splitting long messages
DISCORD_CHUNK_SIZE = 1900
TELEGRAM_CHUNK_SIZE = 3900

# Time constants (seconds)
CONTEXT_RESET_THRESHOLD = 86400  # 24 hours

# History limits
MAX_HISTORY_MESSAGES = 300
MAX_EMOJIS_IN_CONTEXT = 50

# Digest constants
DEFAULT_MAX_TOPICS = 10
MAX_TOPICS_LIMIT = 50
MAX_TOPIC_LENGTH = 100
MAX_HEADLINE_HISTORY = 50
MAX_RECENT_HEADLINES_DISPLAY = 20
DIGEST_SEARCH_COUNT = 5
THREAD_ARCHIVE_DURATION_MINUTES = 1440  # 24 hours

# Discord-specific limits
DISCORD_EMBED_FIELD_LIMIT = 1024

# Summarization threshold
SUMMARIZATION_THRESHOLD_DISCORD = 10
SUMMARIZATION_THRESHOLD_TELEGRAM = 2
