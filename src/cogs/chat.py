import discord
from discord.ext import commands
from typing import override
import logging
import json
from datetime import datetime
from ..services.ai import ai_service
from ..services.db import db
from ..services.search import search_service
from ..utils.chunker import chunk_text

logger = logging.getLogger("grok.chat")

class Chat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    @override
    async def on_ready(self) -> None:
        logger.info(f'Cog {self.__class__.__name__} is ready.')

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
                        if time_diff > 900: # 15 minutes gap
                            # Insert a divider marker in the history to signal a break
                            # We insert it at the beginning of the list (which is the chronological "middle" of the gap)
                            history.insert(0, {"role": "system", "content": "[--- Conversation Gap (>15m) ---]"})
                            
                            # Optional: If the gap is huge (> 1 hour), maybe stop fetching history entirely?
                            if time_diff > 3600:
                                break
                    
                    last_msg_time = msg.created_at
                    
                    role = "assistant" if msg.author == self.bot.user else "user"
                    content = msg.content.replace(f"<@{self.bot.user.id}>", "").strip()
                    if content:
                        history.insert(0, {"role": role, "content": content})

                # Limit effective history to last 10 items after filtering to keep prompt concise
                if len(history) > 10:
                    history = history[-10:]

                base_persona = await db.get_guild_persona(message.guild.id) if message.guild else "You are a helpful assistant."
                
                # Inject Date & Focus Instruction
                current_date = datetime.now().strftime("%Y-%m-%d")
                system_prompt = (
                    f"Current Date: {current_date}\n{base_persona}\n\n"
                    "INSTRUCTION: Focus primarily on the user's latest message. "
                    "Use the chat history ONLY for context if relevant. "
                    "If the latest request is unrelated to previous messages, treat it as a new topic."
                )

                # Construct Message Content (Multimodal)
                user_content = [{"type": "text", "text": clean_content}]
                
                # Add images if present
                for attachment in message.attachments:
                    if attachment.content_type and attachment.content_type.startswith("image/"):
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
        
        ai_msg = await ai_service.generate_response(
            system_prompt=system_prompt,
            user_message=prompt
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
                    user_message=f"{prompt}\n\n[Search Results]: {search_result}",
                    tools=False
                )
                await ctx.followup.send(final_msg.content)
        else:
            await ctx.respond(ai_msg.content)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Chat(bot))
