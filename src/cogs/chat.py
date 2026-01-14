import discord
from discord.ext import commands
from typing import override
import logging
import json
from datetime import datetime
from ..services.ai import ai_service
from ..services.db import db
from ..services.tools import tool_registry
from ..services.chat_service import chat_service
from ..services.emoji_manager import emoji_manager
from ..utils.chunker import chunk_text
from ..utils.constants import Platform, SUMMARIZATION_THRESHOLD_DISCORD

logger = logging.getLogger("grok.chat")


class Chat(commands.Cog):
    """
    Discord Cog for handling chat interactions with the AI.
    Features:
    - Message history management
    - Persona handling
    - Multimodal support (images/GIFs)
    - Tool execution (e.g. web search)
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._ready_executed = False

    @commands.Cog.listener()
    @override
    async def on_ready(self) -> None:
        if self._ready_executed:
            return
        self._ready_executed = True
        logger.info(f'Cog {self.__class__.__name__} is ready.')
        # Trigger background emoji analysis
        for guild in self.bot.guilds:
            self.bot.loop.create_task(self._analyze_emojis_safe(guild))

    async def _analyze_emojis_safe(self, guild: discord.Guild) -> None:
        try:
            count = await emoji_manager.analyze_guild_emojis(guild)
            if count > 0:
                logger.info(f"Analyzed {count} emojis for {guild.name}")
        except Exception as e:
            logger.error(f"Emoji analysis failed for {guild.name}: {e}")

    def _get_clean_content(self, message: discord.Message) -> str:
        clean_content = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
        return clean_content if clean_content else "Hello!"

    async def _build_message_history(self, message: discord.Message) -> list[dict]:
        """Build message history from channel, delegating to chat_service."""
        from ..types import ChatMessage
        
        messages = []
        
        async for msg in message.channel.history(limit=300, before=message):
            if msg.author.bot and msg.author != self.bot.user:
                continue
            
            messages.append(ChatMessage(
                id=msg.id,
                role="assistant" if msg.author == self.bot.user else "user",
                content=msg.content.replace(f"<@{self.bot.user.id}>", "").strip(),
                author_id=msg.author.id,
                timestamp=msg.created_at
            ))
        
        return await chat_service.build_message_history(
            messages=messages,
            bot_id=self.bot.user.id
        )

    async def _check_and_reset_persona(self, message: discord.Message) -> bool:
        """Check for time gap and reset persona if needed."""
        last_previous_msg = None
        async for m in message.channel.history(limit=2, before=message):
            last_previous_msg = m
            break
        
        if last_previous_msg:
            return await chat_service.check_and_reset_persona(
                channel_id=message.channel.id,
                guild_id=message.guild.id,
                last_message_time=last_previous_msg.created_at,
                current_message_time=message.created_at
            )
        return False

    async def _build_user_message_content(self, message: discord.Message, clean_content: str) -> list[dict]:
        """Build multimodal user content using chat_service."""
        images = []
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image/"):
                try:
                    image_data = await attachment.read()
                    images.append((image_data, attachment.content_type))
                except Exception as e:
                    logger.error(f"Failed to read attachment: {e}")
        
        return await chat_service.build_user_content(
            text=clean_content,
            user_id=message.author.id,
            images=images if images else None
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        if self.bot.user.mentioned_in(message) and not message.mention_everyone:
            clean_content = self._get_clean_content(message)

            async with message.channel.typing():
                history = await self._build_message_history(message)
                
                # Fetch Summary
                summary_data = await db.get_channel_summary(message.channel.id)
                current_summary = summary_data['content'] if summary_data else ""
                
                reset_triggered = await self._check_and_reset_persona(message)
                if reset_triggered:
                    await message.channel.send("⏳ *It's been a while. Reverting to my default personality.*")

                base_persona = await db.get_guild_persona(message.guild.id) if message.guild else "You are a helpful assistant."
                emoji_context = await db.get_guild_emojis_context(message.guild.id) if message.guild else ""
                
                # Build system prompt using chat_service
                system_prompt = await chat_service.build_system_prompt(
                    base_persona=base_persona,
                    platform=Platform.DISCORD,
                    current_summary=current_summary,
                    emoji_context=emoji_context
                )

                user_content = await self._build_user_message_content(message, clean_content)
                
                # First AI Call
                ai_msg = await ai_service.generate_response(
                    system_prompt=system_prompt,
                    user_message=user_content,
                    history=history
                )

                # Tool Execution using chat_service
                if ai_msg.tool_calls:
                    async def send_status(text: str) -> None:
                        # Convert markdown italic to Discord format
                        await message.channel.send(text)
                    
                    response_text = await chat_service.handle_tool_calls(
                        ai_msg=ai_msg,
                        system_prompt=system_prompt,
                        user_message=clean_content,
                        history=history,
                        send_status=send_status,
                        context={"guild_id": message.guild.id if message.guild else None}
                    )
                else:
                    response_text = ai_msg.content

                # Split and send chunks if too long
                for chunk in chunk_text(response_text):
                    await message.reply(chunk, mention_author=False)

                # Background Summarization Check
                last_summarized_id = summary_data['last_msg_id'] if summary_data else 0
                unsummarized_msgs = [m for m in history if m.get('id', 0) > last_summarized_id]
                
                if len(unsummarized_msgs) >= SUMMARIZATION_THRESHOLD_DISCORD:
                    self.bot.loop.create_task(
                        chat_service.update_summary(message.channel.id, current_summary, unsummarized_msgs)
                    )

    @discord.slash_command(name="chat", description="Start a new chat thread with Grok")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def chat(self, ctx: discord.ApplicationContext, prompt: str) -> None:
        await ctx.defer()
        
        system_prompt = await db.get_guild_persona(ctx.guild.id) if ctx.guild else "You are a helpful assistant."
        
        clean_content_with_name = f"[{ctx.author.id}]: {prompt}"
        
        ai_msg = await ai_service.generate_response(
            system_prompt=system_prompt,
            user_message=clean_content_with_name
        )

        if ai_msg.tool_calls:
            async def send_status(text: str) -> None:
                await ctx.followup.send(text)
            
            response_text = await chat_service.handle_tool_calls(
                ai_msg=ai_msg,
                system_prompt=system_prompt,
                user_message=clean_content_with_name,
                history=[],
                send_status=send_status,
                context={"guild_id": ctx.guild.id if ctx.guild else None}
            )
            await ctx.followup.send(response_text)
        else:
            await ctx.respond(ai_msg.content)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Chat(bot))
