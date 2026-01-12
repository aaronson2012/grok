import aiosqlite
import logging
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
        """
        try:
            await self.conn.executescript(schema)
            await self.conn.commit()
            
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
             "You are Grok, a witty and helpful AI companion. You are not the xAI Grok. Respond naturally."),
            ("Coder", "A focused programming mentor.", 
             "You are a Senior Software Engineer. Focus on clean code, best practices, and explaining complex topics simply."),
            ("Storyteller", "Creative and descriptive.", 
             "You are a creative storyteller. Use vivid imagery and narrative structure in your responses.")
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

db = Database()
