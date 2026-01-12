import pytest
from unittest.mock import AsyncMock, MagicMock
from src.services.ai import AIService

@pytest.fixture
def mock_openai_client(mocker):
    # Mock the AsyncOpenAI class where it is imported in src.services.ai
    mock_client_cls = mocker.patch("src.services.ai.AsyncOpenAI")
    mock_instance = mock_client_cls.return_value
    
    # Mock chat.completions.create
    mock_instance.chat.completions.create = AsyncMock()
    return mock_instance

@pytest.fixture
def ai_service(mock_openai_client):
    # Re-initialize to use the mocked client
    return AIService()

@pytest.mark.asyncio
async def test_generate_response_success(ai_service, mock_openai_client):
    # Setup mock response
    mock_message = MagicMock()
    mock_message.content = "Hello, world!"
    mock_message.tool_calls = None
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=mock_message)]
    
    mock_openai_client.chat.completions.create.return_value = mock_response

    # Call method
    result = await ai_service.generate_response("System", "User")
    
    assert result.content == "Hello, world!"
    mock_openai_client.chat.completions.create.assert_called_once()
    
    # Verify args
    call_args = mock_openai_client.chat.completions.create.call_args[1]
    assert call_args["messages"][0]["content"] == "System"
    assert call_args["messages"][1]["content"] == "User"

@pytest.mark.asyncio
async def test_generate_response_with_history(ai_service, mock_openai_client):
    mock_message = MagicMock()
    mock_message.content = "Response"
    mock_openai_client.chat.completions.create.return_value = MagicMock(choices=[MagicMock(message=mock_message)])
    
    history = [{"role": "assistant", "content": "Hi"}]
    await ai_service.generate_response("Sys", "User", history=history)
    
    call_args = mock_openai_client.chat.completions.create.call_args[1]
    messages = call_args["messages"]
    assert len(messages) == 3 # Sys, Hist, User
    assert messages[1]["content"] == "Hi"

@pytest.mark.asyncio
async def test_generate_response_failure(ai_service, mock_openai_client):
    # Simulate API error
    mock_openai_client.chat.completions.create.side_effect = Exception("API Error")
    
    # Should not raise, but return fallback
    result = await ai_service.generate_response("Sys", "User")
    
    assert "I'm having trouble thinking" in result.content
