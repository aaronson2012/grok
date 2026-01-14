import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_db():
    with patch("src.cogs.digest.db") as mock:
        mock.conn = MagicMock()
        mock.conn.execute = AsyncMock()
        mock.conn.commit = AsyncMock()
        mock.get_recent_digest_headlines = AsyncMock(return_value=[])
        mock.save_digest_headline = AsyncMock()
        mock.log_error = AsyncMock()
        yield mock


@pytest.fixture
def digest_cog(mock_bot, mock_db):
    with patch("src.cogs.digest.digest_service"):
        from src.cogs.digest import Digest
        cog = Digest(mock_bot)
        cog.digest_loop.cancel()
        return cog


@pytest.mark.asyncio
async def test_add_topic_rejects_empty(digest_cog, mock_application_context):
    with patch("src.services.digest_service.digest_service") as mock_service:
        mock_service.add_topic = AsyncMock(return_value=(False, "Topic cannot be empty."))
        await digest_cog.add_topic.callback(digest_cog, mock_application_context, "   ")
        
        mock_application_context.respond.assert_called_once()
        call_args = mock_application_context.respond.call_args
        assert "empty" in str(call_args).lower() or "❌" in str(call_args)


@pytest.mark.asyncio
async def test_set_time_validates_format(digest_cog, mock_application_context):
    with patch("src.services.digest_service.digest_service") as mock_service:
        mock_service.set_daily_time = AsyncMock(return_value=(False, "Invalid format. Please use HH:MM"))
        await digest_cog.set_time.callback(digest_cog, mock_application_context, "invalid")
        
        mock_application_context.respond.assert_called_once()
        call_args = mock_application_context.respond.call_args
        assert "Invalid format" in str(call_args) or "HH:MM" in str(call_args)


@pytest.mark.asyncio
async def test_set_max_topics_validates_range(digest_cog, mock_application_context):
    await digest_cog.set_max_topics.callback(digest_cog, mock_application_context, 100)
    
    mock_application_context.respond.assert_called_once()
    call_args = mock_application_context.respond.call_args
    assert "between 1 and" in str(call_args) or "50" in str(call_args)


@pytest.mark.asyncio
async def test_set_timezone_rejects_invalid(digest_cog, mock_application_context):
    with patch("src.services.digest_service.digest_service") as mock_service:
        mock_service.set_timezone = AsyncMock(return_value=(False, "Invalid timezone."))
        await digest_cog.set_timezone.callback(digest_cog, mock_application_context, "Invalid/Timezone")
        
        mock_application_context.respond.assert_called_once()
        call_args = mock_application_context.respond.call_args
        assert "Invalid timezone" in str(call_args) or "❌" in str(call_args)
