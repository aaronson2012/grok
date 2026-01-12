import discord
import logging
from .ai import ai_service
from .db import db

logger = logging.getLogger("grok.emojis")

class EmojiManager:
    async def analyze_guild_emojis(self, guild: discord.Guild):
        """
        Scans guild emojis, identifies ones missing from DB, and analyzes them with AI.
        """
        # Get all current emojis
        current_emojis = {e.id: e for e in guild.emojis}
        
        # Check which are already in DB
        async with db.conn.execute("SELECT emoji_id FROM emojis WHERE guild_id = ?", (guild.id,)) as cursor:
            existing_ids = {row['emoji_id'] for row in await cursor.fetchall()}
            
        # Filter for new ones
        new_emojis = [e for e in guild.emojis if e.id not in existing_ids]
        
        if not new_emojis:
            return 0
            
        logger.info(f"Analyzing {len(new_emojis)} new emojis for guild {guild.name}")
        
        count = 0
        for emoji in new_emojis:
            try:
                # Get the image URL
                url = str(emoji.url)
                
                # Ask AI to describe it
                prompt = f"Describe this emoji named ':{emoji.name}:' in 3-5 words. Focus on the emotion or object it represents. Be concise."
                
                # Use the existing AI service (multimodal support)
                response_msg = await ai_service.generate_response(
                    system_prompt="You are an emoji analyzer.",
                    user_message=[
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": url}}
                    ]
                )
                
                description = response_msg.content.strip()
                
                # Save to DB
                await db.save_emoji_description(
                    emoji_id=emoji.id,
                    guild_id=guild.id,
                    name=emoji.name,
                    description=description,
                    animated=emoji.animated
                )
                count += 1
                
            except Exception as e:
                logger.error(f"Failed to analyze emoji {emoji.name}: {e}")
                
        return count

emoji_manager = EmojiManager()
