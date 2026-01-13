import aiosqlite
import logging
import traceback
import json
from datetime import datetime
from ..config import config

logger = logging.getLogger("grok.db")

class Database:
    def __init__(self):
        self.db_path = config.DATABASE_PATH
        self.conn = None

    async def connect(self):
        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row
        await self.init_schema()
        logger.info(f"Connected to database at {self.db_path}")

    async def close(self):
        if self.conn:
            await self.conn.close()
            logger.info("Database connection closed")

    async def init_schema(self):
        schema = """
        CREATE TABLE IF NOT EXISTS personas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            system_prompt TEXT NOT NULL,
            is_global BOOLEAN DEFAULT 0,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS guild_configs (
            guild_id INTEGER PRIMARY KEY,
            active_persona_id INTEGER,
            FOREIGN KEY (active_persona_id) REFERENCES personas(id)
        );

        CREATE TABLE IF NOT EXISTS user_prefs (
            user_id INTEGER PRIMARY KEY,
            preferred_persona_id INTEGER,
            verbosity INTEGER DEFAULT 5, -- 1-10 scale
            emoji_level INTEGER DEFAULT 5, -- 1-10 scale
            FOREIGN KEY (preferred_persona_id) REFERENCES personas(id)
        );

        CREATE TABLE IF NOT EXISTS emojis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emoji_id INTEGER,
            guild_id INTEGER,
            name TEXT,
            description TEXT,
            animated BOOLEAN,
            last_analyzed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(emoji_id, guild_id)
        );

        CREATE TABLE IF NOT EXISTS summaries (
            channel_id INTEGER PRIMARY KEY,
            content TEXT,
            last_msg_id INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS error_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            error_type TEXT,
            message TEXT,
            traceback TEXT,
            context TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS digest_configs (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER,
            max_topics INTEGER DEFAULT 10,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS user_digest_settings (
            user_id INTEGER,
            guild_id INTEGER,
            timezone TEXT DEFAULT 'UTC',
            daily_time TEXT DEFAULT '09:00', -- HH:MM format (24h)
            last_sent_at TIMESTAMP,
            PRIMARY KEY (user_id, guild_id)
        );

        CREATE TABLE IF NOT EXISTS digest_topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            topic TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id, guild_id) REFERENCES user_digest_settings(user_id, guild_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS digest_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            topic TEXT NOT NULL,
            headline TEXT NOT NULL,
            url TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_digest_history_lookup 
        ON digest_history(user_id, guild_id, topic, sent_at);
        """
        try:
            await self.conn.executescript(schema)
            await self.conn.commit()
            
            # Migration: max_topics column
            try:
                await self.conn.execute("ALTER TABLE digest_configs ADD COLUMN max_topics INTEGER DEFAULT 10")
                await self.conn.commit()
                logger.info("Applied migration: Added max_topics to digest_configs")
            except Exception:
                pass
            
            # Migration: make channel_id nullable by recreating table
            try:
                async with self.conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='digest_configs'") as cursor:
                    row = await cursor.fetchone()
                    if row and "NOT NULL" in row[0] and "channel_id" in row[0]:
                        await self.conn.executescript("""
                            CREATE TABLE IF NOT EXISTS digest_configs_new (
                                guild_id INTEGER PRIMARY KEY,
                                channel_id INTEGER,
                                max_topics INTEGER DEFAULT 10,
                                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            );
                            INSERT OR IGNORE INTO digest_configs_new SELECT guild_id, channel_id, max_topics, updated_at FROM digest_configs;
                            DROP TABLE digest_configs;
                            ALTER TABLE digest_configs_new RENAME TO digest_configs;
                        """)
                        await self.conn.commit()
                        logger.info("Applied migration: Made channel_id nullable in digest_configs")
            except Exception as e:
                logger.warning(f"Migration check for channel_id failed (may be fine): {e}")
            
            # Seed default personas if table is empty
            async with self.conn.execute("SELECT COUNT(*) FROM personas") as cursor:
                count = (await cursor.fetchone())[0]
                if count == 0:
                    await self._seed_defaults()
                    
        except Exception as e:
            logger.error(f"Failed to initialize schema: {e}")
            raise

    async def _seed_defaults(self):
        defaults = [
            ("Standard", "The helpful and witty default personality.", 
             "You are Grok, a witty and helpful AI companion. You are not the xAI Grok. Respond naturally.")
        ]
        
        await self.conn.executemany(
            "INSERT INTO personas (name, description, system_prompt, is_global) VALUES (?, ?, ?, 1)",
            defaults
        )
        await self.conn.commit()
        logger.info("Seeded default personas")

    # --- Helper Methods ---
    
    async def save_emoji_description(self, emoji_id: int, guild_id: int, name: str, description: str, animated: bool):
        query = """
        INSERT INTO emojis (emoji_id, guild_id, name, description, animated, last_analyzed)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(emoji_id, guild_id) DO UPDATE SET
            description = excluded.description,
            name = excluded.name,
            last_analyzed = CURRENT_TIMESTAMP
        """
        await self.conn.execute(query, (emoji_id, guild_id, name, description, animated))
        await self.conn.commit()

    async def get_guild_emojis_context(self, guild_id: int, limit: int = 50):
        """Returns a formatted string of emoji descriptions for the system prompt."""
        query = "SELECT emoji_id, name, description, animated FROM emojis WHERE guild_id = ? ORDER BY RANDOM() LIMIT ?"
        async with self.conn.execute(query, (guild_id, limit)) as cursor:
            rows = await cursor.fetchall()
            
        if not rows:
            return ""
            
        lines = ["\n[Custom Server Emojis Available - USE THESE NATURALLY]:"]
        for row in rows:
            # Format: <:name:id> or <a:name:id>
            prefix = "a" if row['animated'] else ""
            lines.append(f"- <{prefix}:{row['name']}:{row['emoji_id']}> : {row['description']}")
            
        return "\n".join(lines)

    async def get_channel_summary(self, channel_id: int):
        """Retrieves the stored summary for a channel."""
        query = "SELECT content, last_msg_id FROM summaries WHERE channel_id = ?"
        async with self.conn.execute(query, (channel_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"content": row['content'], "last_msg_id": row['last_msg_id']}
        return None

    async def update_channel_summary(self, channel_id: int, content: str, last_msg_id: int):
        """Updates or inserts a channel summary."""
        query = """
        INSERT INTO summaries (channel_id, content, last_msg_id, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(channel_id) DO UPDATE SET
            content = excluded.content,
            last_msg_id = excluded.last_msg_id,
            updated_at = CURRENT_TIMESTAMP
        """
        await self.conn.execute(query, (channel_id, content, last_msg_id))
        await self.conn.commit()

    async def get_guild_persona(self, guild_id: int):
        query = """
        SELECT p.system_prompt 
        FROM guild_configs g
        JOIN personas p ON g.active_persona_id = p.id
        WHERE g.guild_id = ?
        """
        async with self.conn.execute(query, (guild_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return row['system_prompt']
        
        # Fallback to 'Standard' if no config
        async with self.conn.execute("SELECT system_prompt FROM personas WHERE name = 'Standard'") as cursor:
            row = await cursor.fetchone()
            return row['system_prompt'] if row else "You are a helpful assistant."

    async def log_error(self, error: Exception, context: dict = None):
        """
        Logs an exception to the database with context.
        """
        try:
            error_type = type(error).__name__
            message = str(error)
            tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            context_json = json.dumps(context, default=str) if context else "{}"
            
            query = """
            INSERT INTO error_logs (error_type, message, traceback, context)
            VALUES (?, ?, ?, ?)
            """
            await self.conn.execute(query, (error_type, message, tb, context_json))
            await self.conn.commit()
            logger.error(f"Logged error to DB: {error_type}: {message}")
        except Exception as e:
            # Fallback if DB logging fails (e.g. DB locked or closed)
            logger.error(f"Failed to log error to DB: {e}")
            logger.error(f"Original error: {error}")

db = Database()

async def get_recent_digest_headlines(user_id: int, guild_id: int, topic: str, days: int = 7) -> list[str]:
    query = """
    SELECT headline FROM digest_history 
    WHERE user_id = ? AND guild_id = ? AND topic = ? COLLATE NOCASE
    AND sent_at > datetime('now', ?)
    ORDER BY sent_at DESC
    LIMIT 50
    """
    async with db.conn.execute(query, (user_id, guild_id, topic, f'-{days} days')) as cursor:
        rows = await cursor.fetchall()
    return [row['headline'] for row in rows]

async def save_digest_headline(user_id: int, guild_id: int, topic: str, headline: str, url: str = None):
    query = """
    INSERT INTO digest_history (user_id, guild_id, topic, headline, url)
    VALUES (?, ?, ?, ?, ?)
    """
    await db.conn.execute(query, (user_id, guild_id, topic, headline, url))
    await db.conn.commit()

async def cleanup_old_digest_history(days: int = 30):
    query = "DELETE FROM digest_history WHERE sent_at < datetime('now', ?)"
    await db.conn.execute(query, (f'-{days} days',))
    await db.conn.commit()
