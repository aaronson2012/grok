import pytest
import pytest_asyncio
import aiosqlite
from src.services.db import Database

@pytest_asyncio.fixture
async def test_db():
    db = Database()
    db.db_path = ":memory:" # Override path for testing
    await db.connect()
    yield db
    await db.close()

@pytest.mark.asyncio
async def test_init_schema(test_db):
    # Check if tables exist
    async with test_db.conn.execute("SELECT name FROM sqlite_master WHERE type='table';") as cursor:
        tables = await cursor.fetchall()
        table_names = [row['name'] for row in tables]
        assert "personas" in table_names
        assert "guild_configs" in table_names
        assert "user_prefs" in table_names
        assert "emojis" in table_names

@pytest.mark.asyncio
async def test_seed_defaults(test_db):
    async with test_db.conn.execute("SELECT * FROM personas WHERE name = 'Standard'") as cursor:
        row = await cursor.fetchone()
        assert row is not None
        assert "helpful" in row['description']

@pytest.mark.asyncio
async def test_save_and_retrieve_emoji(test_db):
    await test_db.save_emoji_description(123, 456, "funny_cat", "A cat laughing", False)
    
    # Check direct retrieval
    async with test_db.conn.execute("SELECT * FROM emojis WHERE emoji_id = 123") as cursor:
        row = await cursor.fetchone()
        assert row['name'] == "funny_cat"
        assert row['description'] == "A cat laughing"

    # Check context helper
    context = await test_db.get_guild_emojis_context(456)
    assert ":funny_cat:123" in context
    assert "A cat laughing" in context

@pytest.mark.asyncio
async def test_persona_management(test_db):
    # Test getting default persona when none set
    prompt = await test_db.get_guild_persona(999)
    assert "You are Grok" in prompt # From seeded default

    # Create new persona
    await test_db.conn.execute(
        "INSERT INTO personas (name, description, system_prompt, is_global) VALUES (?, ?, ?, ?)",
        ("TestBot", "Test desc", "You are a test bot.", 1)
    )
    await test_db.conn.commit()
    
    # Get ID
    async with test_db.conn.execute("SELECT id FROM personas WHERE name='TestBot'") as cursor:
        pid = (await cursor.fetchone())['id']

    # Set as active
    await test_db.conn.execute(
        "INSERT INTO guild_configs (guild_id, active_persona_id) VALUES (?, ?)", 
        (999, pid)
    )
    await test_db.conn.commit()

    # Verify retrieval
    prompt = await test_db.get_guild_persona(999)
    assert prompt == "You are a test bot."
