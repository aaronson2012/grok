import pytest
import httpx
from unittest.mock import AsyncMock, patch
from src.services.search import SearchService

@pytest.fixture
def search_service():
    service = SearchService()
    service.api_key = "test_key"
    return service

@pytest.mark.asyncio
async def test_search_success(search_service):
    mock_response = {
        "results": [
            {
                "title": "Test Result",
                "snippet": "This is a test",
                "url": "http://example.com"
            }
        ]
    }
    
    with patch("httpx.AsyncClient") as MockClient:
        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = AsyncMock(
            status_code=200,
            json=lambda: mock_response,
            raise_for_status=lambda: None
        )
        MockClient.return_value.__aenter__.return_value = mock_client_instance
        MockClient.return_value.__aexit__.return_value = None

        result = await search_service.search("test query")
        
        assert "- **Test Result**" in result
        assert "This is a test" in result
        assert "<http://example.com>" in result

@pytest.mark.asyncio
async def test_search_no_api_key():
    service = SearchService()
    service.api_key = None
    result = await service.search("test")
    assert "Error: Perplexity API key is not configured" in result

@pytest.mark.asyncio
async def test_search_error(search_service):
    with patch("httpx.AsyncClient") as MockClient:
        mock_client_instance = AsyncMock()
        mock_client_instance.post.side_effect = Exception("Network Error")
        
        MockClient.return_value.__aenter__.return_value = mock_client_instance
        MockClient.return_value.__aexit__.return_value = None

        result = await search_service.search("fail")
        assert "Search failed" in result
