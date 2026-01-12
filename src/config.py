import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-3-flash-preview")
    BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY")
    DATABASE_PATH = os.getenv("DATABASE_PATH", "data/grok.db")
    
    @classmethod
    def validate(cls):
        if not cls.DISCORD_TOKEN:
            raise ValueError("DISCORD_TOKEN is missing")
        if not cls.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is missing")
        # Brave key is optional but search won't work without it
        if not cls.BRAVE_SEARCH_API_KEY:
            print("WARNING: BRAVE_SEARCH_API_KEY is missing. Search will fail.")

config = Config()
