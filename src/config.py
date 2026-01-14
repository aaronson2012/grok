import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-3-flash-preview")
    OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
    PERPLEXITY_BASE_URL = os.getenv("PERPLEXITY_BASE_URL", "https://api.perplexity.ai/search")
    DATABASE_PATH = os.getenv("DATABASE_PATH", "data/grok.db")
    DEBUG_GUILD_IDS = [int(g) for g in os.getenv("DEBUG_GUILD_IDS", "").split(",") if g.strip()]
    TELEGRAM_ADMIN_IDS = [int(g) for g in os.getenv("TELEGRAM_ADMIN_IDS", "").split(",") if g.strip()]

    @classmethod
    def _validate_common(cls):
        if not cls.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is missing")
        if not cls.PERPLEXITY_API_KEY:
            print("WARNING: PERPLEXITY_API_KEY is missing. Search will fail.")

    @classmethod
    def validate_discord(cls):
        cls._validate_common()
        if not cls.DISCORD_TOKEN:
            raise ValueError("DISCORD_TOKEN is missing")

    @classmethod
    def validate_telegram(cls):
        cls._validate_common()
        if not cls.TELEGRAM_TOKEN:
            raise ValueError("TELEGRAM_TOKEN is missing")

    @classmethod
    def validate(cls):
        cls.validate_discord()


config = Config()
