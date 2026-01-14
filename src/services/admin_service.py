"""
Admin service for memory and error log management.
Provides platform-agnostic access to admin operations.
"""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiosqlite import Row

from .db import db

logger = logging.getLogger("grok.admin_service")


class AdminService:

    async def get_channel_summary(self, channel_id: int) -> dict[str, str | int] | None:
        async with db.conn.execute(
            "SELECT content, updated_at FROM summaries WHERE channel_id = ?",
            (channel_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return None

        return {"content": row["content"], "updated_at": row["updated_at"]}

    async def clear_channel_summary(self, channel_id: int) -> None:
        await db.conn.execute("DELETE FROM summaries WHERE channel_id = ?", (channel_id,))
        await db.conn.commit()

    async def get_recent_errors(self, limit: int = 5) -> list:
        async with db.conn.execute(
            "SELECT id, error_type, message, created_at FROM error_logs ORDER BY id DESC LIMIT ?",
            (limit,)
        ) as cursor:
            return list(await cursor.fetchall())

    async def clear_all_errors(self) -> None:
        await db.conn.execute("DELETE FROM error_logs")
        await db.conn.commit()

    async def get_error_details(self, error_id: int) -> dict | None:
        async with db.conn.execute(
            "SELECT * FROM error_logs WHERE id = ?",
            (error_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return None

        return {
            "id": row["id"],
            "error_type": row["error_type"],
            "message": row["message"],
            "traceback": row["traceback"],
            "context": row["context"],
            "created_at": row["created_at"],
        }


admin_service = AdminService()
