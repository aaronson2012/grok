import asyncio
import functools
import logging

logger = logging.getLogger("grok.utils")

def async_retry(retries: int = 3, delay: float = 1.0, backoff: float = 2.0, exceptions: tuple = (Exception,)):
    """
    Decorator to retry an async function upon exception.
    
    Args:
        retries: Max number of retries (total attempts = retries + 1).
        delay: Initial sleep time in seconds.
        backoff: Multiplier for delay after each failure.
        exceptions: Tuple of exception types to catch and retry on.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = delay
            for attempt in range(retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == retries:
                        logger.error(f"Function {func.__name__} failed after {retries + 1} attempts. Error: {e}")
                        raise e
                    
                    logger.warning(f"Function {func.__name__} failed (Attempt {attempt + 1}/{retries + 1}). Retrying in {current_delay}s... Error: {e}")
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff
        return wrapper
    return decorator
