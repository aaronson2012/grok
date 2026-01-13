import os
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, AsyncMock

os.environ["OPENROUTER_API_KEY"] = "sk-test-key"
os.environ["DISCORD_TOKEN"] = "test-token"
os.environ["PERPLEXITY_API_KEY"] = "test-search-key"
os.environ["DATABASE_PATH"] = ":memory:"

from src.services.db import Database


@pytest_asyncio.fixture
async def test_db():
    db = Database()
    db.db_path = ":memory:"
    await db.connect()
    yield db
    await db.close()


@pytest.fixture
def mock_discord_user():
    user = MagicMock()
    user.id = 123456789
    user.display_name = "TestUser"
    user.discriminator = "1234"
    user.bot = False
    user.mention = "<@123456789>"
    return user


@pytest.fixture
def mock_discord_guild():
    guild = MagicMock()
    guild.id = 987654321
    guild.name = "TestGuild"
    guild.emojis = []
    return guild


@pytest.fixture
def mock_discord_channel():
    channel = MagicMock()
    channel.id = 111222333
    channel.name = "test-channel"
    channel.send = AsyncMock()
    channel.typing = MagicMock(return_value=AsyncMock())
    return channel


@pytest.fixture
def mock_discord_message(mock_discord_user, mock_discord_guild, mock_discord_channel):
    message = MagicMock()
    message.id = 444555666
    message.author = mock_discord_user
    message.guild = mock_discord_guild
    message.channel = mock_discord_channel
    message.content = "Hello @Bot"
    message.attachments = []
    message.created_at = MagicMock()
    message.reply = AsyncMock()
    message.mention_everyone = False
    return message


@pytest.fixture
def mock_application_context(mock_discord_user, mock_discord_guild, mock_discord_channel):
    ctx = MagicMock()
    ctx.author = mock_discord_user
    ctx.user = mock_discord_user
    ctx.guild = mock_discord_guild
    ctx.channel = mock_discord_channel
    ctx.respond = AsyncMock()
    ctx.defer = AsyncMock()
    ctx.followup = MagicMock()
    ctx.followup.send = AsyncMock()
    return ctx


@pytest.fixture
def mock_bot(mock_discord_user):
    bot = MagicMock()
    bot.user = mock_discord_user
    bot.user.id = 999888777
    bot.guilds = []
    bot.loop = MagicMock()
    bot.loop.create_task = MagicMock()
    bot.get_channel = MagicMock(return_value=None)
    bot.fetch_channel = AsyncMock()
    bot.get_user = MagicMock(return_value=None)
    bot.fetch_user = AsyncMock()
    return bot
