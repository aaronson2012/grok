import discord
from discord.ext import commands
from typing import override
import logging
import json
from ..services.ai import ai_service
from ..services.db import db
from ..services.search import search_service

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
                async for msg in message.channel.history(limit=10, before=message):
                    if msg.author.bot and msg.author != self.bot.user:
                        continue
                    
                    role = "assistant" if msg.author == self.bot.user else "user"
                    content = msg.content.replace(f"<@{self.bot.user.id}>", "").strip()
                    if content:
                        history.insert(0, {"role": role, "content": content})

                system_prompt = await db.get_guild_persona(message.guild.id) if message.guild else "You are a helpful assistant."

                # First AI Call
                ai_msg = await ai_service.generate_response(
                    system_prompt=system_prompt,
                    user_message=clean_content,
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

                await message.reply(response_text, mention_author=False)

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
