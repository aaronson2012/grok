import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo
from src.services.digest_service import DigestService


@pytest.fixture
def digest_service():
    return DigestService()


@pytest.fixture
def mock_db():
    with patch("src.services.digest_service.db") as mock:
        mock.conn = MagicMock()
        yield mock


class TestAddTopic:
    @pytest.mark.asyncio
    async def test_add_topic_success(self, digest_service, mock_db):
        mock_db.conn.execute = AsyncMock()
        mock_db.conn.commit = AsyncMock()
        
        # Mock ensure_user_settings
        with patch.object(digest_service, "ensure_user_settings", new=AsyncMock()), \
             patch.object(digest_service, "get_max_topics", new=AsyncMock(return_value=10)), \
             patch.object(digest_service, "get_user_topic_count", new=AsyncMock(return_value=2)), \
             patch.object(digest_service, "topic_exists", new=AsyncMock(return_value=False)):
            
            success, message = await digest_service.add_topic(
                user_id=123, guild_id=456, topic="Python News"
            )
            
            assert success is True
            assert "Added topic" in message
            assert "Python News" in message

    @pytest.mark.asyncio
    async def test_add_topic_empty(self, digest_service):
        success, message = await digest_service.add_topic(
            user_id=123, guild_id=456, topic="   "
        )
        
        assert success is False
        assert "cannot be empty" in message

    @pytest.mark.asyncio
    async def test_add_topic_limit_reached(self, digest_service, mock_db):
        mock_db.conn.execute = AsyncMock()
        mock_db.conn.commit = AsyncMock()
        
        with patch.object(digest_service, "ensure_user_settings", new=AsyncMock()), \
             patch.object(digest_service, "get_max_topics", new=AsyncMock(return_value=5)), \
             patch.object(digest_service, "get_user_topic_count", new=AsyncMock(return_value=5)):
            
            success, message = await digest_service.add_topic(
                user_id=123, guild_id=456, topic="New Topic"
            )
            
            assert success is False
            assert "only have up to 5 topics" in message

    @pytest.mark.asyncio
    async def test_add_topic_duplicate(self, digest_service, mock_db):
        mock_db.conn.execute = AsyncMock()
        mock_db.conn.commit = AsyncMock()
        
        with patch.object(digest_service, "ensure_user_settings", new=AsyncMock()), \
             patch.object(digest_service, "get_max_topics", new=AsyncMock(return_value=10)), \
             patch.object(digest_service, "get_user_topic_count", new=AsyncMock(return_value=2)), \
             patch.object(digest_service, "topic_exists", new=AsyncMock(return_value=True)):
            
            success, message = await digest_service.add_topic(
                user_id=123, guild_id=456, topic="Existing"
            )
            
            assert success is False
            assert "already have" in message

    @pytest.mark.asyncio
    async def test_add_topic_truncates_long_topic(self, digest_service, mock_db):
        mock_db.conn.execute = AsyncMock()
        mock_db.conn.commit = AsyncMock()
        
        with patch.object(digest_service, "ensure_user_settings", new=AsyncMock()), \
             patch.object(digest_service, "get_max_topics", new=AsyncMock(return_value=10)), \
             patch.object(digest_service, "get_user_topic_count", new=AsyncMock(return_value=0)), \
             patch.object(digest_service, "topic_exists", new=AsyncMock(return_value=False)):
            
            long_topic = "A" * 150
            success, message = await digest_service.add_topic(
                user_id=123, guild_id=456, topic=long_topic
            )
            
            assert success is True
            # Topic should be truncated to 100 chars
            call_args = mock_db.conn.execute.call_args_list[-1][0]
            assert len(call_args[1][2]) <= 100


class TestRemoveTopic:
    @pytest.mark.asyncio
    async def test_remove_topic(self, digest_service, mock_db):
        mock_db.conn.execute = AsyncMock()
        mock_db.conn.commit = AsyncMock()
        
        await digest_service.remove_topic(user_id=123, guild_id=456, topic="Python")
        
        mock_db.conn.execute.assert_called_once()
        mock_db.conn.commit.assert_called_once()


class TestGetUserTopics:
    @pytest.mark.asyncio
    async def test_get_user_topics(self, digest_service, mock_db):
        mock_cursor = MagicMock()
        mock_cursor.fetchall = AsyncMock(return_value=[
            {"topic": "Python"},
            {"topic": "AI"},
            {"topic": "Rust"},
        ])
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock()
        mock_db.conn.execute = MagicMock(return_value=mock_cursor)
        
        result = await digest_service.get_user_topics(user_id=123, guild_id=456)
        
        assert result == ["Python", "AI", "Rust"]


class TestSetDailyTime:
    @pytest.mark.asyncio
    async def test_set_daily_time_valid(self, digest_service, mock_db):
        mock_db.conn.execute = AsyncMock()
        mock_db.conn.commit = AsyncMock()
        
        with patch.object(digest_service, "ensure_user_settings", new=AsyncMock()):
            success, message = await digest_service.set_daily_time(
                user_id=123, guild_id=456, time_str="09:30"
            )
            
            assert success is True
            assert "09:30" in message

    @pytest.mark.asyncio
    async def test_set_daily_time_invalid_format(self, digest_service):
        success, message = await digest_service.set_daily_time(
            user_id=123, guild_id=456, time_str="9:30am"
        )
        
        assert success is False
        assert "Invalid format" in message

    @pytest.mark.asyncio
    async def test_set_daily_time_invalid_time(self, digest_service):
        success, message = await digest_service.set_daily_time(
            user_id=123, guild_id=456, time_str="25:00"
        )
        
        assert success is False
        assert "Invalid format" in message


class TestSetTimezone:
    @pytest.mark.asyncio
    async def test_set_timezone_valid(self, digest_service, mock_db):
        mock_db.conn.execute = AsyncMock()
        mock_db.conn.commit = AsyncMock()
        
        with patch.object(digest_service, "ensure_user_settings", new=AsyncMock()):
            success, message = await digest_service.set_timezone(
                user_id=123, guild_id=456, timezone="America/New_York"
            )
            
            assert success is True
            assert "America/New_York" in message

    @pytest.mark.asyncio
    async def test_set_timezone_invalid(self, digest_service):
        success, message = await digest_service.set_timezone(
            user_id=123, guild_id=456, timezone="Invalid/Timezone"
        )
        
        assert success is False
        assert "Invalid timezone" in message


class TestIsDue:
    @pytest.mark.asyncio
    async def test_is_due_returns_true_when_past_time_not_sent_today(self, digest_service):
        tz = ZoneInfo("UTC")
        now = datetime.now(tz)
        
        # Set target time to 1 hour ago
        target_hour = (now.hour - 1) % 24
        target_time = f"{target_hour:02d}:00"
        
        user_row = {
            "user_id": 123,
            "timezone": "UTC",
            "daily_time": target_time,
            "last_sent_at": None,
        }
        
        result = await digest_service.is_due(user_row)
        assert result is True

    @pytest.mark.asyncio
    async def test_is_due_returns_false_before_target_time(self, digest_service):
        tz = ZoneInfo("UTC")
        now = datetime.now(tz)
        
        # Set target time to 1 hour in the future
        target_hour = (now.hour + 1) % 24
        target_time = f"{target_hour:02d}:00"
        
        user_row = {
            "user_id": 123,
            "timezone": "UTC",
            "daily_time": target_time,
            "last_sent_at": None,
        }
        
        result = await digest_service.is_due(user_row)
        assert result is False

    @pytest.mark.asyncio
    async def test_is_due_returns_false_if_sent_today(self, digest_service):
        tz = ZoneInfo("UTC")
        now = datetime.now(tz)
        
        # Set target time to 2 hours ago
        target_hour = (now.hour - 2) % 24
        target_time = f"{target_hour:02d}:00"
        
        # Last sent 1 hour ago (same day)
        last_sent = now.replace(hour=(now.hour - 1) % 24).strftime("%Y-%m-%d %H:%M:%S")
        
        user_row = {
            "user_id": 123,
            "timezone": "UTC",
            "daily_time": target_time,
            "last_sent_at": last_sent,
        }
        
        result = await digest_service.is_due(user_row)
        assert result is False


class TestGetGreeting:
    def test_morning_greeting(self, digest_service):
        assert digest_service.get_greeting(6) == "Good morning"
        assert digest_service.get_greeting(11) == "Good morning"

    def test_afternoon_greeting(self, digest_service):
        assert digest_service.get_greeting(12) == "Good afternoon"
        assert digest_service.get_greeting(17) == "Good afternoon"

    def test_evening_greeting(self, digest_service):
        assert digest_service.get_greeting(18) == "Good evening"
        assert digest_service.get_greeting(23) == "Good evening"
        assert digest_service.get_greeting(4) == "Good evening"


class TestMarkDigestSent:
    @pytest.mark.asyncio
    async def test_mark_digest_sent(self, digest_service, mock_db):
        mock_db.conn.execute = AsyncMock()
        mock_db.conn.commit = AsyncMock()
        
        await digest_service.mark_digest_sent(user_id=123, guild_id=456)
        
        mock_db.conn.execute.assert_called_once()
        mock_db.conn.commit.assert_called_once()
