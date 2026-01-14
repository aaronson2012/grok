"""
Unified persona service for both Discord and Telegram platforms.
Handles persona CRUD operations and AI-assisted persona creation.
"""
import logging
from typing import Any

from .ai import ai_service
from .db import db

logger = logging.getLogger("grok.persona_service")


class PersonaService:
    """
    Platform-agnostic persona management service.
    """

    async def get_all_personas(self) -> list[dict]:
        """Get all personas, with Standard first."""
        async with db.conn.execute(
            "SELECT id, name, description FROM personas WHERE name = 'Standard'"
        ) as cursor:
            standard = await cursor.fetchall()
        
        async with db.conn.execute(
            "SELECT id, name, description FROM personas WHERE name != 'Standard' ORDER BY name"
        ) as cursor:
            others = await cursor.fetchall()
        
        return list(standard) + list(others)

    async def get_deletable_personas(self) -> list[dict]:
        """Get all personas that can be deleted (non-Standard)."""
        async with db.conn.execute(
            "SELECT id, name, description FROM personas WHERE name != 'Standard' ORDER BY name"
        ) as cursor:
            return list(await cursor.fetchall())

    async def get_persona_by_id(self, persona_id: int) -> dict | None:
        """Get a persona by ID."""
        async with db.conn.execute(
            "SELECT id, name, description, system_prompt FROM personas WHERE id = ?",
            (persona_id,)
        ) as cursor:
            return await cursor.fetchone()

    async def get_persona_name(self, persona_id: int) -> str:
        """Get persona name by ID."""
        async with db.conn.execute(
            "SELECT name FROM personas WHERE id = ?",
            (persona_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row['name'] if row else "Unknown"

    async def set_guild_persona(self, guild_id: int, persona_id: int) -> None:
        """Set the active persona for a guild/chat."""
        await db.conn.execute("""
            INSERT INTO guild_configs (guild_id, active_persona_id) 
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET active_persona_id = excluded.active_persona_id
        """, (guild_id, persona_id))
        await db.conn.commit()

    async def get_current_persona(self, guild_id: int) -> dict | None:
        """Get the current active persona for a guild."""
        query = """
        SELECT p.name, p.description 
        FROM guild_configs g
        JOIN personas p ON g.active_persona_id = p.id
        WHERE g.guild_id = ?
        """
        async with db.conn.execute(query, (guild_id,)) as cursor:
            return await cursor.fetchone()

    async def delete_persona(self, persona_id: int) -> str:
        """Delete a persona and return its name."""
        name = await self.get_persona_name(persona_id)
        await db.conn.execute("DELETE FROM personas WHERE id = ?", (persona_id,))
        await db.conn.commit()
        return name

    async def create_persona(
        self,
        user_input: str,
        created_by: int,
        collision_suffix: str | None = None,
    ) -> tuple[bool, dict | str]:
        """
        Create a new persona using AI assistance.
        
        Args:
            user_input: User's description of the persona
            created_by: User ID of creator
            collision_suffix: Suffix to add if name collision (e.g., user's discriminator)
            
        Returns:
            (success, persona_dict or error_message)
        """
        try:
            ai_prompt = (
                f"User Input: '{user_input}'\n\n"
                "Task: Create a Discord bot persona based on this input.\n"
                "Output strictly in this format:\n"
                "NAME: <The direct character name or simple title. Max 15 chars. No spaces. e.g. 'Batman' not 'DarkKnight', 'Mario' not 'Plumber'>\n"
                "DESCRIPTION: <A short 1-sentence summary of who this is>\n"
                "PROMPT: <A 2-3 sentence system instruction. Start with 'You are...'>"
            )
            
            ai_msg = await ai_service.generate_response(
                system_prompt="You are a configuration generator.",
                user_message=ai_prompt
            )
            
            # Parse output
            content = ai_msg.content.strip()
            name = "Unknown"
            description = "Custom Persona"
            prompt = "You are a helpful assistant."
            
            for line in content.split('\n'):
                if line.startswith("NAME:"):
                    name = line.replace("NAME:", "").strip()[:50]
                elif line.startswith("DESCRIPTION:"):
                    description = line.replace("DESCRIPTION:", "").strip()[:200]
                elif line.startswith("PROMPT:"):
                    prompt = line.replace("PROMPT:", "").strip()
            
            # Fallback if parsing fails
            if name == "Unknown":
                name = user_input.split()[0][:15]
                description = user_input[:50]
            
            # Check uniqueness
            async with db.conn.execute(
                "SELECT 1 FROM personas WHERE name = ? COLLATE NOCASE",
                (name,)
            ) as cursor:
                if await cursor.fetchone():
                    if collision_suffix:
                        name = f"{name}_{collision_suffix}"
                    else:
                        name = f"{name}_{created_by % 10000}"

            await db.conn.execute("""
                INSERT INTO personas (name, description, system_prompt, is_global, created_by)
                VALUES (?, ?, ?, 0, ?)
            """, (name, description, prompt, created_by))
            await db.conn.commit()
            
            return True, {
                "name": name,
                "description": description,
                "system_prompt": prompt
            }
            
        except Exception as e:
            logger.error(f"Persona creation failed: {e}")
            return False, "Creation failed. Please try again."


# Singleton instance
persona_service = PersonaService()
