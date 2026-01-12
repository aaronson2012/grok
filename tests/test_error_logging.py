import pytest
import pytest_asyncio
from src.services.db import Database

@pytest_asyncio.fixture
async def test_db():
    db = Database()
    db.db_path = ":memory:"
    await db.connect()
    yield db
    await db.close()

@pytest.mark.asyncio
async def test_log_error(test_db):
    try:
        1 / 0
    except ZeroDivisionError as e:
        await test_db.log_error(e, {"user_id": 123})
        
    async with test_db.conn.execute("SELECT * FROM error_logs") as cursor:
        row = await cursor.fetchone()
        assert row is not None
        assert row['error_type'] == "ZeroDivisionError"
        assert "division by zero" in row['message']
        assert "user_id" in row['context']
        assert "123" in row['context']
        assert row['traceback'] is not None
