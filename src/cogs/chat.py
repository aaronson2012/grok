import discord
from discord.ext import commands
from typing import override
import logging
import json
import base64
import io
from PIL import Image
from datetime import datetime
from ..services.ai import ai_service
from ..services.db import db
from ..services.tools import tool_registry
from ..services.emoji_manager import emoji_manager
from ..utils.chunker import chunk_text

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

    @commands.Cog.listener()
    @override
    async def on_ready(self) -> None:
        logger.info(f'Cog {self.__class__.__name__} is ready.')
        # Trigger background emoji analysis
        # In a real production app, this should be a task loop or queue
        for guild in self.bot.guilds:
            self.bot.loop.create_task(self._analyze_emojis_safe(guild))

    async def _analyze_emojis_safe(self, guild):
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
        history = []
        last_msg_time = None
        
        async for msg in message.channel.history(limit=20, before=message):
            if msg.author.bot and msg.author != self.bot.user:
                continue
            
            if last_msg_time:
                time_diff = (last_msg_time - msg.created_at).total_seconds()
                if time_diff > 3600:
                    pass
            
            last_msg_time = msg.created_at
            role = "assistant" if msg.author == self.bot.user else "user"
            content = msg.content.replace(f"<@{self.bot.user.id}>", "").strip()
            
            if role == "user":
                content = f"[{msg.author.id}]: {content}"
                
            if content:
                history.insert(0, {"role": role, "content": content})
        return history

    async def _check_and_reset_persona(self, message: discord.Message) -> bool:
        last_previous_msg = None
        async for m in message.channel.history(limit=2, before=message):
            last_previous_msg = m
            break
        
        if last_previous_msg:
            gap = (message.created_at - last_previous_msg.created_at).total_seconds()
            if gap > 3600:
                async with db.conn.execute("SELECT id FROM personas WHERE name = 'Standard'") as cursor:
                    row = await cursor.fetchone()
                    if row:
                        await db.conn.execute("""
                            INSERT INTO guild_configs (guild_id, active_persona_id) 
                            VALUES (?, ?)
                            ON CONFLICT(guild_id) DO UPDATE SET active_persona_id = excluded.active_persona_id
                        """, (message.guild.id, row['id']))
                        await db.conn.commit()
                        return True
        return False

    async def _build_user_message_content(self, message: discord.Message, clean_content: str) -> list[dict]:
        clean_content_with_name = f"[{message.author.id}]: {clean_content}"
        user_content = [{"type": "text", "text": clean_content_with_name}]
        
        for attachment in message.attachments:
            if attachment.content_type:
                if "image/gif" in attachment.content_type:
                    try:
                        image_data = await attachment.read()
                        with Image.open(io.BytesIO(image_data)) as img:
                            if getattr(img, "is_animated", False):
                                middle_frame = img.n_frames // 2
                                img.seek(middle_frame)
                            
                            output_buffer = io.BytesIO()
                            img.convert("RGB").save(output_buffer, format="JPEG")
                            output_buffer.seek(0)
                            
                            base64_image = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
                            data_url = f"data:image/jpeg;base64,{base64_image}"
                            
                            user_content.append({
                                "type": "image_url",
                                "image_url": {"url": data_url}
                            })
                    except Exception as e:
                        logger.error(f"Failed to process GIF: {e}")
                        user_content.append({
                            "type": "image_url",
                            "image_url": {"url": attachment.url}
                        })
                elif attachment.content_type.startswith("image/"):
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": attachment.url}
                    })
        return user_content

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
                
                # Inject Date, Focus, and Memory
                current_date = datetime.now().strftime("%Y-%m-%d")
                memory_block = f"\n[PREVIOUS CONVERSATION SUMMARY]:\n{current_summary}\n" if current_summary else ""
                
                system_prompt = (
                    f"Current Date: {current_date}\n{base_persona}\n{emoji_context}\n{memory_block}\n"
                    "INSTRUCTION: Focus primarily on the user's latest message. "
                    "Use the chat history ONLY for context if relevant. "
                    "If the latest request is unrelated to previous messages, treat it as a new topic. "
                    "Users are identified by [User ID] at the start of their messages. "
                    "To address a user, use the format <@User ID>. Do NOT use their display name in brackets. "
                    "Example: If you see '[12345]: Hello', reply with 'Hi <@12345>!'. "
                    "IMPORTANT: Keep your response concise and under 1900 characters to fit in a Discord message. "
                    "Use emojis naturally (about once every 2-3 sentences). Use a mix of standard Unicode emojis and the provided Custom Server Emojis. "
                    "Prefer the Custom Emojis when they fit the specific context or emotion perfectly."
                )

                user_content = await self._build_user_message_content(message, clean_content)
                
                # First AI Call
                ai_msg = await ai_service.generate_response(
                    system_prompt=system_prompt,
                    user_message=user_content,
                    history=history
                )

                # Tool Execution Loop
                if ai_msg.tool_calls:
                    tool_call = ai_msg.tool_calls[0]
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    
                    # Optional: User feedback
                    if func_name == "web_search":
                        query = args.get("query", "something")
                        await message.channel.send(f"🔎 Searching for: *{query}*...")
                    elif func_name == "calculator":
                        expr = args.get("expression", "math")
                        await message.channel.send(f"🧮 Calculating: *{expr}*...")
                    else:
                        await message.channel.send(f"🤖 Using tool: *{func_name}*...")

                    try:
                        tool_result = await tool_registry.execute(func_name, args)
                    except Exception as e:
                        tool_result = f"Error executing tool {func_name}: {e}"
                        # Log tool failure to DB
                        await db.log_error(e, {"context": "Tool Execution", "tool": func_name, "args": args, "guild_id": message.guild.id if message.guild else None})
                        
                    # Add the search context to the history for the final answer
                    context_injection = f"Tool Output for '{func_name}':\n{tool_result}"
                    history.append({"role": "system", "content": context_injection})
                    
                    # Second AI Call
                    final_msg = await ai_service.generate_response(
                        system_prompt=system_prompt,
                        user_message=clean_content, # Re-send original prompt with added context
                        history=history,
                        tools=False # Prevent infinite loops
                    )
                    response_text = final_msg.content
                else:
                    response_text = ai_msg.content

                # Split and send chunks if too long
                for chunk in chunk_text(response_text):
                    await message.reply(chunk, mention_author=False)

                # Background Summarization Check
                # We check if we have enough unsummarized history.
                # Since we don't store messages, we just check if history length > 15
                # And if the last summary update was "a while ago" (implied by content change).
                # Simpler: If history > 10, trigger summary update of the *oldest* 5 messages + current summary.
                
                if len(history) > 10:
                    self.bot.loop.create_task(self._update_summary(message.channel, current_summary, history))

    async def _update_summary(self, channel, current_summary, history):
        try:
            # Take the oldest 5 messages from history to summarize
            # History format: [{'role': 'user', 'content': '...'}, ...]
            to_summarize = []
            for msg in history[:5]: # Oldest 5
                role = msg['role']
                content = msg['content']
                to_summarize.append(f"{role}: {content}")
            
            new_summary = await ai_service.summarize_conversation(current_summary, to_summarize)
            
            # Use the ID of the last message we summarized to track position
            # Ideally we'd parse the ID from the content string "[ID]: text"
            # But for now, we just update the content.
            # In a robust system, we'd use message IDs.
            
            await db.update_channel_summary(channel.id, new_summary, 0)
            logger.info(f"Updated summary for channel {channel.name}")
            
        except Exception as e:
            logger.error(f"Failed to update summary: {e}")

    @discord.slash_command(name="chat", description="Start a new chat thread with Grok")
    async def chat(self, ctx: discord.ApplicationContext, prompt: str) -> None:
        await ctx.defer()
        
        system_prompt = await db.get_guild_persona(ctx.guild.id) if ctx.guild else "You are a helpful assistant."
        
        clean_content_with_name = f"[{ctx.author.id}]: {prompt}"
        
        ai_msg = await ai_service.generate_response(
            system_prompt=system_prompt,
            user_message=clean_content_with_name
        )

        if ai_msg.tool_calls:
             tool_call = ai_msg.tool_calls[0]
             func_name = tool_call.function.name
             args = json.loads(tool_call.function.arguments)
             
             if func_name == "web_search":
                query = args.get("query", "something")
                await ctx.followup.send(f"🔎 Searching for: *{query}*...")
             else:
                await ctx.followup.send(f"🤖 Using tool: *{func_name}*...")

             try:
                tool_result = await tool_registry.execute(func_name, args)
             except Exception as e:
                tool_result = f"Error: {e}"
             
             # Simple recursion for Slash Command
             final_msg = await ai_service.generate_response(
                 system_prompt=system_prompt,
                 user_message=f"{clean_content_with_name}\n\n[Tool Output ({func_name})]: {tool_result}",
                 tools=False
             )
             await ctx.followup.send(final_msg.content)
        else:
            await ctx.respond(ai_msg.content)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Chat(bot))
