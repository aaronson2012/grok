"""
Unified digest service for both Discord and Telegram platforms.
Handles digest generation, topic management, and scheduling logic.
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

from .ai import ai_service
from .db import db
from .search import search_service
from ..utils.chunker import chunk_text
from ..utils.constants import DEFAULT_MAX_TOPICS, Platform

logger = logging.getLogger("grok.digest_service")


class DigestService:
    """
    Platform-agnostic digest service.
    Handles all digest-related business logic.
    """

    async def ensure_user_settings(self, user_id: int, guild_id: int) -> None:
        """Ensure user has digest settings entry."""
        await db.conn.execute("""
            INSERT OR IGNORE INTO user_digest_settings (user_id, guild_id) 
            VALUES (?, ?)
        """, (user_id, guild_id))
        await db.conn.commit()

    async def get_max_topics(self, guild_id: int) -> int:
        """Get the max topics limit for a guild."""
        async with db.conn.execute(
            "SELECT max_topics FROM digest_configs WHERE guild_id = ?",
            (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row and row['max_topics']:
                return row['max_topics']
        return DEFAULT_MAX_TOPICS

    async def get_user_topic_count(self, user_id: int, guild_id: int) -> int:
        """Get the number of topics a user has."""
        async with db.conn.execute(
            "SELECT COUNT(*) FROM digest_topics WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        ) as cursor:
            return (await cursor.fetchone())[0]

    async def topic_exists(self, user_id: int, guild_id: int, topic: str) -> bool:
        """Check if a topic already exists for user."""
        async with db.conn.execute(
            "SELECT 1 FROM digest_topics WHERE user_id = ? AND guild_id = ? AND topic = ? COLLATE NOCASE",
            (user_id, guild_id, topic)
        ) as cursor:
            return await cursor.fetchone() is not None

    async def add_topic(self, user_id: int, guild_id: int, topic: str) -> tuple[bool, str]:
        """
        Add a topic for a user.
        
        Returns:
            (success, message) tuple
        """
        topic = topic[:100].strip()
        if not topic:
            return False, "Topic cannot be empty."
        
        await self.ensure_user_settings(user_id, guild_id)
        
        limit = await self.get_max_topics(guild_id)
        count = await self.get_user_topic_count(user_id, guild_id)
        
        if count >= limit:
            return False, f"You can only have up to {limit} topics."
        
        if await self.topic_exists(user_id, guild_id, topic):
            return False, f"You already have **{topic}** in your list."
        
        await db.conn.execute(
            "INSERT INTO digest_topics (user_id, guild_id, topic) VALUES (?, ?, ?)",
            (user_id, guild_id, topic)
        )
        await db.conn.commit()
        return True, f"Added topic: **{topic}**"

    async def remove_topic(self, user_id: int, guild_id: int, topic: str) -> None:
        """Remove a topic for a user."""
        await db.conn.execute(
            "DELETE FROM digest_topics WHERE user_id = ? AND guild_id = ? AND topic = ?",
            (user_id, guild_id, topic)
        )
        await db.conn.commit()

    async def get_user_topics(self, user_id: int, guild_id: int) -> list[str]:
        """Get all topics for a user."""
        async with db.conn.execute(
            "SELECT topic FROM digest_topics WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        ) as cursor:
            rows = await cursor.fetchall()
        return [row['topic'] for row in rows]

    async def set_daily_time(self, user_id: int, guild_id: int, time_str: str) -> tuple[bool, str]:
        """Set daily digest time."""
        try:
            datetime.strptime(time_str, "%H:%M")
        except ValueError:
            return False, "Invalid format. Please use HH:MM (e.g., 09:00 or 14:30)."
        
        await self.ensure_user_settings(user_id, guild_id)
        
        await db.conn.execute("""
            UPDATE user_digest_settings 
            SET daily_time = ? 
            WHERE user_id = ? AND guild_id = ?
        """, (time_str, user_id, guild_id))
        await db.conn.commit()
        
        return True, f"Daily digest time set to **{time_str}**."

    async def set_timezone(self, user_id: int, guild_id: int, timezone: str) -> tuple[bool, str]:
        """Set user's timezone."""
        try:
            ZoneInfo(timezone)
        except Exception:
            return False, "Invalid timezone. Try 'UTC', 'America/New_York', 'Europe/London', etc."
        
        await self.ensure_user_settings(user_id, guild_id)
        
        await db.conn.execute("""
            UPDATE user_digest_settings 
            SET timezone = ? 
            WHERE user_id = ? AND guild_id = ?
        """, (timezone, user_id, guild_id))
        await db.conn.commit()
        
        return True, f"Timezone set to **{timezone}**."

    async def get_user_timezone(self, user_id: int, guild_id: int) -> str:
        """Get user's timezone."""
        async with db.conn.execute(
            "SELECT timezone FROM user_digest_settings WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row['timezone'] if row else 'UTC'

    async def is_due(self, user_row: Any) -> bool:
        """Determines if a user is due for their digest."""
        try:
            tz = ZoneInfo(user_row['timezone'])
            now = datetime.now(tz)
            
            target_h, target_m = map(int, user_row['daily_time'].split(':'))
            target_time = now.replace(hour=target_h, minute=target_m, second=0, microsecond=0)
            
            if now < target_time:
                return False
            
            # Check last sent
            if user_row['last_sent_at']:
                last_sent = user_row['last_sent_at']
                if isinstance(last_sent, str):
                    try:
                        last_sent_dt = datetime.fromisoformat(last_sent)
                    except ValueError:
                        last_sent_dt = datetime.strptime(last_sent, "%Y-%m-%d %H:%M:%S")
                    
                    last_sent_dt = last_sent_dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
                else:
                    last_sent_dt = last_sent.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)

                if last_sent_dt.date() == now.date():
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking if due for user {user_row['user_id']}: {e}")
            return False

    def get_greeting(self, hour: int) -> str:
        """Get time-appropriate greeting."""
        if 5 <= hour < 12:
            return "Good morning"
        elif 12 <= hour < 18:
            return "Good afternoon"
        else:
            return "Good evening"

    async def generate_topic_digest(
        self,
        user_id: int,
        guild_id: int,
        topic: str,
    ) -> tuple[str | None, str]:
        """
        Generate digest content for a single topic.
        
        Returns:
            (section_title, content) or (None, "NO_NEW_DEVELOPMENTS")
        """
        recent_headlines = await db.get_recent_digest_headlines(user_id, guild_id, topic)
        
        search_results = await search_service.search(f"{topic} news today", count=5)
        
        if "No results found" in search_results:
            return topic.title(), "No recent news found."

        history_context = ""
        if recent_headlines:
            history_context = (
                "\n\nPreviously reported stories (DO NOT repeat these):\n"
                + "\n".join(f"- {h}" for h in recent_headlines[:20])
            )

        prompt = (
            f"Topic: {topic}\n"
            f"Search Results:\n{search_results}"
            f"{history_context}\n\n"
            "Task: Write a short, engaging summary of NEW news for this topic. "
            "Skip any stories similar to the previously reported ones. "
            "If ALL stories in the search results are repeats or very similar to previously reported ones, "
            "simply respond with: NO_NEW_DEVELOPMENTS\n\n"
            "Otherwise, include 1-2 key links if available. "
            "Format with Markdown. Do NOT include greetings.\n"
            "IMPORTANT: Keep markdown links on a SINGLE LINE - never break [text](url) across lines.\n\n"
            "Start your response with a clean, title-cased section header for this topic. "
            "Format: SECTION_TITLE: Your Polished Title Here\n"
            "Example: If topic is 'ai vibe coding', use 'SECTION_TITLE: AI Vibe Coding' or 'SECTION_TITLE: The Rise of Vibe Coding'\n\n"
            "At the end, list the headlines you covered in this format:\n"
            "HEADLINES_COVERED:\n- headline 1\n- headline 2"
        )
        
        ai_response = await ai_service.generate_response(
            system_prompt="You are a news anchor providing a daily digest. Jump straight into the news. Avoid repeating old stories.",
            user_message=prompt
        )
        
        content = ai_response.content
        
        if "NO_NEW_DEVELOPMENTS" in content:
            return topic.title(), "No new developments since the last update."
        
        # Parse response
        section_title = topic.title()
        display_content = content
        
        if "SECTION_TITLE:" in content:
            lines = content.split("\n", 1)
            first_line = lines[0]
            if "SECTION_TITLE:" in first_line:
                section_title = first_line.split("SECTION_TITLE:", 1)[1].strip()
                display_content = lines[1] if len(lines) > 1 else ""
        
        # Extract and save headlines
        headlines_to_save = []
        if "HEADLINES_COVERED:" in display_content:
            parts = display_content.split("HEADLINES_COVERED:")
            display_content = parts[0].strip()
            if len(parts) > 1:
                for line in parts[1].strip().split("\n"):
                    line = line.strip().lstrip("-").strip()
                    if line:
                        headlines_to_save.append(line)
        
        for headline in headlines_to_save:
            await db.save_digest_headline(user_id, guild_id, topic, headline)
        
        return section_title, display_content

    async def mark_digest_sent(self, user_id: int, guild_id: int) -> None:
        """Mark that a digest was sent to user."""
        await db.conn.execute("""
            UPDATE user_digest_settings 
            SET last_sent_at = CURRENT_TIMESTAMP 
            WHERE user_id = ? AND guild_id = ?
        """, (user_id, guild_id))
        await db.conn.commit()


# Singleton instance
digest_service = DigestService()
