import os
import pytest

# Set dummy env vars for testing BEFORE importing any modules
os.environ["OPENROUTER_API_KEY"] = "sk-test-key"
os.environ["DISCORD_TOKEN"] = "test-token"
os.environ["BRAVE_SEARCH_API_KEY"] = "test-search-key"
os.environ["DATABASE_PATH"] = ":memory:"
