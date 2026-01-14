import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.chat_service import ChatService
from src.types import ChatMessage
from src.utils.constants import Platform, CONTEXT_RESET_THRESHOLD


@pytest.fixture
def chat_service():
    return ChatService()


class TestBuildSystemPrompt:
    @pytest.mark.asyncio
    async def test_discord_platform_basic(self, chat_service):
        result = await chat_service.build_system_prompt(
            base_persona="You are a test bot.",
            platform=Platform.DISCORD,
        )
        
        assert "You are a test bot." in result
        assert "1900 characters" in result
        assert "Discord message" in result
        assert "<@User ID>" in result

    @pytest.mark.asyncio
    async def test_telegram_platform_basic(self, chat_service):
        result = await chat_service.build_system_prompt(
            base_persona="You are a test bot.",
            platform=Platform.TELEGRAM,
        )
        
        assert "You are a test bot." in result
        assert "3900 characters" in result
        assert "Telegram message" in result
        assert "<@User ID>" not in result

    @pytest.mark.asyncio
    async def test_with_summary(self, chat_service):
        result = await chat_service.build_system_prompt(
            base_persona="You are a test bot.",
            platform=Platform.DISCORD,
            current_summary="Previous conversation about cats.",
        )
        
        assert "[PREVIOUS CONVERSATION SUMMARY]" in result
        assert "Previous conversation about cats." in result

    @pytest.mark.asyncio
    async def test_with_emoji_context_discord(self, chat_service):
        emoji_context = "Custom Emojis: :happy:123"
        result = await chat_service.build_system_prompt(
            base_persona="You are a test bot.",
            platform=Platform.DISCORD,
            emoji_context=emoji_context,
        )
        
        assert emoji_context in result
        assert "Custom Server Emojis" in result

    @pytest.mark.asyncio
    async def test_emoji_context_ignored_telegram(self, chat_service):
        emoji_context = "Custom Emojis: :happy:123"
        result = await chat_service.build_system_prompt(
            base_persona="You are a test bot.",
            platform=Platform.TELEGRAM,
            emoji_context=emoji_context,
        )
        
        # Emoji block is included but no instruction about custom emojis
        assert "Custom Server Emojis" not in result


class TestBuildMessageHistory:
    @pytest.mark.asyncio
    async def test_basic_history(self, chat_service):
        now = datetime.now()
        messages = [
            ChatMessage(id=1, role="user", author_id=100, content="Hello", timestamp=now - timedelta(minutes=5)),
            ChatMessage(id=2, role="assistant", author_id=999, content="Hi there!", timestamp=now - timedelta(minutes=4)),
            ChatMessage(id=3, role="user", author_id=100, content="How are you?", timestamp=now - timedelta(minutes=3)),
        ]
        
        result = await chat_service.build_message_history(messages, bot_id=999)
        
        assert len(result) == 3
        assert result[0]["role"] == "user"
        assert "[100]:" in result[0]["content"]
        assert result[1]["role"] == "assistant"
        assert result[2]["role"] == "user"

    @pytest.mark.asyncio
    async def test_respects_max_messages(self, chat_service):
        now = datetime.now()
        messages = [
            ChatMessage(id=i, role="user", author_id=100, content=f"Msg {i}", timestamp=now - timedelta(minutes=i))
            for i in range(10)
        ]
        
        result = await chat_service.build_message_history(messages, bot_id=999, max_messages=5)
        
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_context_reset_on_time_gap(self, chat_service):
        now = datetime.now()
        old_time = now - timedelta(seconds=CONTEXT_RESET_THRESHOLD + 100)
        
        messages = [
            ChatMessage(id=1, role="user", author_id=100, content="Old message", timestamp=old_time),
            ChatMessage(id=2, role="user", author_id=100, content="Recent message", timestamp=now),
        ]
        
        result = await chat_service.build_message_history(messages, bot_id=999)
        
        # Should only include the recent message (context reset)
        assert len(result) == 1
        assert "Recent message" in result[0]["content"]

    @pytest.mark.asyncio
    async def test_includes_all_messages_even_empty_original_content(self, chat_service):
        now = datetime.now()
        messages = [
            ChatMessage(id=1, role="user", author_id=100, content="Hello", timestamp=now),
            ChatMessage(id=2, role="user", author_id=100, content="", timestamp=now),
            ChatMessage(id=3, role="user", author_id=100, content="World", timestamp=now),
        ]
        
        result = await chat_service.build_message_history(messages, bot_id=999)
        
        assert len(result) == 3


class TestProcessImageToBase64:
    @pytest.mark.asyncio
    async def test_processes_jpeg(self, chat_service):
        # Create a minimal valid JPEG (1x1 pixel red)
        from PIL import Image
        import io
        
        img = Image.new("RGB", (10, 10), color="red")
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG")
        image_data = buffer.getvalue()
        
        result = await chat_service.process_image_to_base64(image_data)
        
        assert result.startswith("data:image/jpeg;base64,")
        assert len(result) > 50  # Has actual data

    @pytest.mark.asyncio
    async def test_processes_png(self, chat_service):
        from PIL import Image
        import io
        
        img = Image.new("RGBA", (10, 10), color="blue")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        image_data = buffer.getvalue()
        
        result = await chat_service.process_image_to_base64(image_data)
        
        assert result.startswith("data:image/jpeg;base64,")  # Converted to JPEG


class TestBuildUserContent:
    @pytest.mark.asyncio
    async def test_text_only(self, chat_service):
        result = await chat_service.build_user_content(
            text="Hello world",
            user_id=12345,
        )
        
        assert len(result) == 1
        assert result[0]["type"] == "text"
        assert "[12345]: Hello world" in result[0]["text"]

    @pytest.mark.asyncio
    async def test_with_image(self, chat_service):
        from PIL import Image
        import io
        
        img = Image.new("RGB", (10, 10), color="green")
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG")
        image_data = buffer.getvalue()
        
        result = await chat_service.build_user_content(
            text="Check this image",
            user_id=12345,
            images=[(image_data, "image/jpeg")],
        )
        
        assert len(result) == 2
        assert result[0]["type"] == "text"
        assert result[1]["type"] == "image_url"
        assert "data:image/jpeg;base64," in result[1]["image_url"]["url"]


class TestHandleToolCalls:
    @pytest.mark.asyncio
    async def test_web_search_tool(self, chat_service):
        mock_ai_msg = MagicMock()
        mock_ai_msg.tool_calls = [MagicMock()]
        mock_ai_msg.tool_calls[0].function.name = "web_search"
        mock_ai_msg.tool_calls[0].function.arguments = '{"query": "test query"}'
        
        mock_send_status = AsyncMock()
        
        with patch("src.services.chat_service.tool_registry") as mock_registry, \
             patch("src.services.chat_service.ai_service") as mock_ai:
            mock_registry.execute = AsyncMock(return_value="Search results here")
            mock_final = MagicMock()
            mock_final.content = "Final response"
            mock_ai.generate_response = AsyncMock(return_value=mock_final)
            
            result = await chat_service.handle_tool_calls(
                ai_msg=mock_ai_msg,
                system_prompt="System",
                user_message="User message",
                history=[],
                send_status=mock_send_status,
            )
            
            assert result == "Final response"
            mock_send_status.assert_called_once()
            assert "Searching for" in mock_send_status.call_args[0][0]
            mock_registry.execute.assert_called_once_with("web_search", {"query": "test query"})

    @pytest.mark.asyncio
    async def test_calculator_tool(self, chat_service):
        mock_ai_msg = MagicMock()
        mock_ai_msg.tool_calls = [MagicMock()]
        mock_ai_msg.tool_calls[0].function.name = "calculator"
        mock_ai_msg.tool_calls[0].function.arguments = '{"expression": "2+2"}'
        
        mock_send_status = AsyncMock()
        
        with patch("src.services.chat_service.tool_registry") as mock_registry, \
             patch("src.services.chat_service.ai_service") as mock_ai:
            mock_registry.execute = AsyncMock(return_value="4")
            mock_final = MagicMock()
            mock_final.content = "The answer is 4"
            mock_ai.generate_response = AsyncMock(return_value=mock_final)
            
            result = await chat_service.handle_tool_calls(
                ai_msg=mock_ai_msg,
                system_prompt="System",
                user_message="What is 2+2?",
                history=[],
                send_status=mock_send_status,
            )
            
            assert result == "The answer is 4"
            assert "Calculating" in mock_send_status.call_args[0][0]


class TestUpdateSummary:
    @pytest.mark.asyncio
    async def test_updates_summary(self, chat_service):
        with patch("src.services.chat_service.ai_service") as mock_ai, \
             patch("src.services.chat_service.db") as mock_db:
            mock_ai.summarize_conversation = AsyncMock(return_value="New summary")
            mock_db.update_channel_summary = AsyncMock()
            
            messages = [
                {"role": "user", "content": "Hello", "id": 123},
                {"role": "assistant", "content": "Hi!", "id": 124},
            ]
            
            await chat_service.update_summary(
                channel_id=999,
                current_summary="Old summary",
                messages=messages,
            )
            
            mock_ai.summarize_conversation.assert_called_once()
            mock_db.update_channel_summary.assert_called_once_with(999, "New summary", 124)

    @pytest.mark.asyncio
    async def test_skips_empty_messages(self, chat_service):
        with patch("src.services.chat_service.ai_service") as mock_ai:
            await chat_service.update_summary(
                channel_id=999,
                current_summary="Old summary",
                messages=[],
            )
            
            mock_ai.summarize_conversation.assert_not_called()
