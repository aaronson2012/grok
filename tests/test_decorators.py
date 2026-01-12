import pytest
import asyncio
from unittest.mock import AsyncMock
from src.utils.decorators import async_retry

@pytest.mark.asyncio
async def test_async_retry_success():
    mock_func = AsyncMock(return_value="Success")
    
    @async_retry(retries=2, delay=0.01)
    async def decorated():
        return await mock_func()
        
    result = await decorated()
    assert result == "Success"
    assert mock_func.call_count == 1

@pytest.mark.asyncio
async def test_async_retry_failure_then_success():
    mock_func = AsyncMock(side_effect=[ValueError("Fail 1"), "Success"])
    
    @async_retry(retries=2, delay=0.01)
    async def decorated():
        return await mock_func()
        
    result = await decorated()
    assert result == "Success"
    assert mock_func.call_count == 2

@pytest.mark.asyncio
async def test_async_retry_max_retries_exceeded():
    mock_func = AsyncMock(side_effect=ValueError("Persistent Failure"))
    
    @async_retry(retries=2, delay=0.01)
    async def decorated():
        return await mock_func()
    
    with pytest.raises(ValueError, match="Persistent Failure"):
        await decorated()
    
    assert mock_func.call_count == 3 # Initial + 2 retries

@pytest.mark.asyncio
async def test_async_retry_specific_exception():
    # Should retry on ValueError, but raise TypeError immediately
    mock_func = AsyncMock(side_effect=TypeError("Wrong Type"))
    
    @async_retry(retries=2, delay=0.01, exceptions=(ValueError,))
    async def decorated():
        return await mock_func()
    
    with pytest.raises(TypeError):
        await decorated()
        
    assert mock_func.call_count == 1
