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
from ..services.search import search_service
from ..services.emoji_manager import emoji_manager
from ..utils.chunker import chunk_text

logger = logging.getLogger("grok.chat")

class Chat(commands.Cog):
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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        if self.bot.user.mentioned_in(message) and not message.mention_everyone:
            clean_content = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
            if not clean_content:
                clean_content = "Hello!"

            async with message.channel.typing():
                history = []
                last_msg_time = None
                
                # Fetch more messages to allow for filtering
                async for msg in message.channel.history(limit=20, before=message):
                    if msg.author.bot and msg.author != self.bot.user:
                        continue
                    
                    # Time-Gating Logic
                    # If this message is > 60 minutes older than the one after it (which we processed previously), 
                    # we consider the context stale beyond this point.
                    # Note: We are iterating backwards (newest to oldest).
                    
                    if last_msg_time:
                        time_diff = (last_msg_time - msg.created_at).total_seconds()
                        if time_diff > 3600: # 1 hour gap
                            # Reset to Default Persona if gap is too large
                            # We check if this gap is occurring *now* (i.e. between now and the last message)
                            # Actually, we need to check if the *last message in the channel* was > 1 hour ago.
                            pass
                    
                    last_msg_time = msg.created_at
                    
                    role = "assistant" if msg.author == self.bot.user else "user"
                    content = msg.content.replace(f"<@{self.bot.user.id}>", "").strip()
                    
                    if role == "user":
                        content = f"[{msg.author.display_name}]: {content}"
                        
                    if content:
                        history.insert(0, {"role": role, "content": content})

                # Check time since VERY LAST message to determine if we should reset persona
                # We need to find the timestamp of the message *before* the current one.
                # Since we just iterated, history[-1] is the previous message in prompt context, 
                # but let's check the actual channel history for accuracy.
                
                # Logic: If the previous message in the channel (ignoring the one just sent) is > 1 hour old, reset.
                last_previous_msg = None
                async for m in message.channel.history(limit=2, before=message):
                    last_previous_msg = m
                    break # Just get one
                
                reset_triggered = False
                if last_previous_msg:
                    gap = (message.created_at - last_previous_msg.created_at).total_seconds()
                    if gap > 3600:
                        # Reset Persona to Standard
                        # We need to get the Standard ID first
                        async with db.conn.execute("SELECT id FROM personas WHERE name = 'Standard'") as cursor:
                            row = await cursor.fetchone()
                            if row:
                                await db.conn.execute("""
                                    INSERT INTO guild_configs (guild_id, active_persona_id) 
                                    VALUES (?, ?)
                                    ON CONFLICT(guild_id) DO UPDATE SET active_persona_id = excluded.active_persona_id
                                """, (message.guild.id, row['id']))
                                await db.conn.commit()
                                reset_triggered = True
                                await message.channel.send("⏳ *It's been a while. Reverting to my default personality.*")

                base_persona = await db.get_guild_persona(message.guild.id) if message.guild else "You are a helpful assistant."
                emoji_context = await db.get_guild_emojis_context(message.guild.id) if message.guild else ""
                
                # Inject Date & Focus Instruction
                current_date = datetime.now().strftime("%Y-%m-%d")
                system_prompt = (
                    f"Current Date: {current_date}\n{base_persona}\n{emoji_context}\n\n"
                    "INSTRUCTION: Focus primarily on the user's latest message. "
                    "Use the chat history ONLY for context if relevant. "
                    "If the latest request is unrelated to previous messages, treat it as a new topic. "
                    "Users are identified by [Name] at the start of their messages. Address them by name when appropriate. "
                    "IMPORTANT: Keep your response concise and under 1900 characters to fit in a Discord message. "
                    "Use emojis naturally (about once every 2-3 sentences). Use a mix of standard Unicode emojis and the provided Custom Server Emojis. "
                    "Prefer the Custom Emojis when they fit the specific context or emotion perfectly."
                )

                # Construct Message Content (Multimodal)
                clean_content_with_name = f"[{message.author.display_name}]: {clean_content}"
                user_content = [{"type": "text", "text": clean_content_with_name}]
                
                # Add images if present
                for attachment in message.attachments:
                    if attachment.content_type:
                        if "image/gif" in attachment.content_type:
                            try:
                                # Process GIF
                                image_data = await attachment.read()
                                with Image.open(io.BytesIO(image_data)) as img:
                                    # Calculate middle frame
                                    if getattr(img, "is_animated", False):
                                        middle_frame = img.n_frames // 2
                                        img.seek(middle_frame)
                                    
                                    # Save frame to buffer
                                    output_buffer = io.BytesIO()
                                    # Convert to RGB to ensure compatibility (in case of palette mode)
                                    img.convert("RGB").save(output_buffer, format="JPEG")
                                    output_buffer.seek(0)
                                    
                                    # Convert to base64
                                    base64_image = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
                                    data_url = f"data:image/jpeg;base64,{base64_image}"
                                    
                                    user_content.append({
                                        "type": "image_url",
                                        "image_url": {"url": data_url}
                                    })
                            except Exception as e:
                                logger.error(f"Failed to process GIF: {e}")
                                # Fallback to original URL if processing fails
                                user_content.append({
                                    "type": "image_url",
                                    "image_url": {"url": attachment.url}
                                })
                        elif attachment.content_type.startswith("image/"):
                            user_content.append({
                                "type": "image_url",
                                "image_url": {"url": attachment.url}
                            })

                # First AI Call
                ai_msg = await ai_service.generate_response(
                    system_prompt=system_prompt,
                    user_message=user_content,
                    history=history
                )

                # Tool Execution Loop
                if ai_msg.tool_calls:
                    # Add the initial AI thought (tool call) to history context for the next turn
                    # Note: We can't easily modify the 'history' list structure expected by 'generate_response' 
                    # because it expects simple dicts. We need to construct the conversation flow.
                    
                    # For simplicity in this iteration:
                    # 1. Execute tool
                    # 2. Feed result back as a system/tool output
                    # 3. Get final answer
                    
                    tool_call = ai_msg.tool_calls[0]
                    if tool_call.function.name == "web_search":
                        args = json.loads(tool_call.function.arguments)
                        query = args.get("query")
                        
                        await message.channel.send(f"🔎 Searching for: *{query}*...")
                        
                        search_result = search_service.search(query)
                        
                        # Add the search context to the history for the final answer
                        # We append it as a user message or system injection for simplicity with OpenRouter
                        # "Tool" role support depends on the provider, so we'll inject it as context.
                        context_injection = f"Tool Output for '{query}':\n{search_result}"
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
                        response_text = "I tried to use a tool I don't know."
                else:
                    response_text = ai_msg.content

                # Split and send chunks if too long
                for chunk in chunk_text(response_text):
                    await message.reply(chunk, mention_author=False)

    @discord.slash_command(name="chat", description="Start a new chat thread with Grok")
    async def chat(self, ctx: discord.ApplicationContext, prompt: str) -> None:
        await ctx.defer()
        
        system_prompt = await db.get_guild_persona(ctx.guild.id) if ctx.guild else "You are a helpful assistant."
        
        clean_content_with_name = f"[{ctx.author.display_name}]: {prompt}"
        
        ai_msg = await ai_service.generate_response(
            system_prompt=system_prompt,
            user_message=clean_content_with_name
        )

        if ai_msg.tool_calls:
             tool_call = ai_msg.tool_calls[0]
             if tool_call.function.name == "web_search":
                args = json.loads(tool_call.function.arguments)
                query = args.get("query")
                
                await ctx.followup.send(f"🔎 Searching for: *{query}*...")
                search_result = search_service.search(query)
                
                # Simple recursion for Slash Command
                final_msg = await ai_service.generate_response(
                    system_prompt=system_prompt,
                    user_message=f"{clean_content_with_name}\n\n[Search Results]: {search_result}",
                    tools=False
                )
                await ctx.followup.send(final_msg.content)
        else:
            await ctx.respond(ai_msg.content)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Chat(bot))
