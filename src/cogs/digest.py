import discord
from discord.ext import commands, tasks
from discord.commands import SlashCommandGroup
import logging
from datetime import datetime, timedelta
import zoneinfo
from zoneinfo import ZoneInfo
from typing import List, Optional

from ..services.db import db
from ..services.ai import ai_service
from ..services.search import search_service

logger = logging.getLogger("grok.digest")

class Digest(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.processing_users = set()
        self.digest_loop.start()

    def cog_unload(self):
        self.digest_loop.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f'Cog {self.__class__.__name__} is ready.')

    digest = SlashCommandGroup("digest", "Manage your daily news digest")
    topics = digest.create_subgroup("topics", "Manage your digest topics")
    config = digest.create_subgroup("config", "Configure digest settings")

    # --- Configuration Commands ---

    @config.command(name="max_topics", description="Set the maximum number of digest topics per user (Admin only)")
    @discord.default_permissions(administrator=True)
    async def set_max_topics(self, ctx: discord.ApplicationContext, limit: int):
        if limit < 1 or limit > 50:
            await ctx.respond("❌ Limit must be between 1 and 50.", ephemeral=True)
            return

        await db.conn.execute("""
            INSERT INTO digest_configs (guild_id, max_topics) 
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET max_topics = excluded.max_topics
        """, (ctx.guild.id, limit))
        await db.conn.commit()
        await ctx.respond(f"✅ Max topics per user set to **{limit}**.")

    @config.command(name="channel", description="Set the channel where digests will be posted (Admin only)")
    @discord.default_permissions(administrator=True)
    async def set_channel(self, ctx: discord.ApplicationContext, channel: discord.TextChannel):
        await db.conn.execute("""
            INSERT INTO digest_configs (guild_id, channel_id) 
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id
        """, (ctx.guild.id, channel.id))
        await db.conn.commit()
        await ctx.respond(f"✅ Digest channel set to {channel.mention}")

    @config.command(name="time", description="Set your daily digest time (24h format, e.g., 09:00)")
    async def set_time(self, ctx: discord.ApplicationContext, time_str: str):
        try:
            datetime.strptime(time_str, "%H:%M")
        except ValueError:
            await ctx.respond("❌ Invalid format. Please use HH:MM (e.g., 09:00 or 14:30).", ephemeral=True)
            return

        await self._ensure_user_settings(ctx.user.id, ctx.guild.id)
        
        await db.conn.execute("""
            UPDATE user_digest_settings 
            SET daily_time = ? 
            WHERE user_id = ? AND guild_id = ?
        """, (time_str, ctx.user.id, ctx.guild.id))
        await db.conn.commit()
        
        await ctx.respond(f"✅ Daily digest time set to **{time_str}**.")

    @config.command(name="timezone", description="Set your timezone (e.g., UTC, America/New_York)")
    async def set_timezone(self, ctx: discord.ApplicationContext, timezone: str):
        try:
            ZoneInfo(timezone)
        except Exception:
            await ctx.respond("❌ Invalid timezone. Try 'UTC', 'America/New_York', 'Europe/London', etc.", ephemeral=True)
            return

        await self._ensure_user_settings(ctx.user.id, ctx.guild.id)

        await db.conn.execute("""
            UPDATE user_digest_settings 
            SET timezone = ? 
            WHERE user_id = ? AND guild_id = ?
        """, (timezone, ctx.user.id, ctx.guild.id))
        await db.conn.commit()

        await ctx.respond(f"✅ Timezone set to **{timezone}**.")

    # --- Topic Commands ---

    @topics.command(name="add", description="Add a topic to your digest")
    async def add_topic(self, ctx: discord.ApplicationContext, topic: str):
        await self._ensure_user_settings(ctx.user.id, ctx.guild.id)
        
        limit = 10
        async with db.conn.execute("SELECT max_topics FROM digest_configs WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
            row = await cursor.fetchone()
            if row and row['max_topics']:
                limit = row['max_topics']

        # Check current count to prevent spam
        async with db.conn.execute("SELECT COUNT(*) FROM digest_topics WHERE user_id = ? AND guild_id = ?", (ctx.user.id, ctx.guild.id)) as cursor:
            count = (await cursor.fetchone())[0]
            if count >= limit:
                await ctx.respond(f"❌ You can only have up to {limit} topics (Server Limit).", ephemeral=True)
                return
        
        # Check for duplicates
        async with db.conn.execute("SELECT 1 FROM digest_topics WHERE user_id = ? AND guild_id = ? AND topic = ? COLLATE NOCASE", (ctx.user.id, ctx.guild.id, topic)) as cursor:
            if await cursor.fetchone():
                await ctx.respond(f"⚠️ You already have **{topic}** in your list.", ephemeral=True)
                return

        await db.conn.execute("INSERT INTO digest_topics (user_id, guild_id, topic) VALUES (?, ?, ?)", (ctx.user.id, ctx.guild.id, topic))
        await db.conn.commit()
        await ctx.respond(f"✅ Added topic: **{topic}**")

    @topics.command(name="remove", description="Remove a topic from your digest")
    async def remove_topic(self, ctx: discord.ApplicationContext, topic: str):
        await db.conn.execute("DELETE FROM digest_topics WHERE user_id = ? AND guild_id = ? AND topic = ?", (ctx.user.id, ctx.guild.id, topic))
        await db.conn.commit()
        await ctx.respond(f"✅ Removed topic: **{topic}**")

    @topics.command(name="list", description="List your digest topics")
    async def list_topics(self, ctx: discord.ApplicationContext):
        async with db.conn.execute("SELECT topic FROM digest_topics WHERE user_id = ? AND guild_id = ?", (ctx.user.id, ctx.guild.id)) as cursor:
            rows = await cursor.fetchall()
            
        if not rows:
            await ctx.respond("You have no topics set. Use `/digest topics add` to get started.")
            return

        topics_list = "\n".join([f"• {row['topic']}" for row in rows])
        await ctx.respond(f"**Your Digest Topics:**\n{topics_list}")

    @digest.command(name="now", description="Trigger your daily digest immediately (for testing)")
    async def trigger_now(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        
        # Concurrency check
        if ctx.user.id in self.processing_users:
            await ctx.followup.send("⏳ Your digest is already being generated! Please wait.")
            return

        result = await self.send_digest(ctx.guild.id, ctx.user.id)
        if result:
            await ctx.followup.send("✅ Digest sent!")
        else:
            await ctx.followup.send("❌ Could not send digest. Check if you have topics and a configured channel.")

    # --- Background Loop ---

    @tasks.loop(minutes=1)
    async def digest_loop(self):
        """Checks every minute for users due for a digest."""
        try:
            # Iterate over all guilds that have a configured channel
            async with db.conn.execute("SELECT guild_id FROM digest_configs") as cursor:
                guilds = await cursor.fetchall()

            for guild_row in guilds:
                guild_id = guild_row['guild_id']
                
                # Find users in this guild who need a digest
                # Condition: current_time_in_user_tz >= daily_time AND (last_sent < today_in_user_tz)
                # This is tricky in SQL, so we iterate users and check in Python
                query = """
                    SELECT user_id, timezone, daily_time, last_sent_at 
                    FROM user_digest_settings 
                    WHERE guild_id = ?
                """
                async with db.conn.execute(query, (guild_id,)) as user_cursor:
                    users = await user_cursor.fetchall()
                    
                for user in users:
                    if await self._is_due(user):
                        await self.send_digest(guild_id, user['user_id'])
                        
        except Exception as e:
            logger.error(f"Error in digest loop: {e}")
            await db.log_error(e, {"context": "digest_loop"})

    @digest_loop.before_loop
    async def before_digest_loop(self):
        await self.bot.wait_until_ready()

    # --- Helpers ---

    async def _ensure_user_settings(self, user_id: int, guild_id: int):
        await db.conn.execute("""
            INSERT OR IGNORE INTO user_digest_settings (user_id, guild_id) 
            VALUES (?, ?)
        """, (user_id, guild_id))
        await db.conn.commit()

    async def _is_due(self, user_row) -> bool:
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

    async def send_digest(self, guild_id: int, user_id: int) -> bool:
        """Generates and sends the digest."""
        if user_id in self.processing_users:
            logger.info(f"Skipping digest for {user_id} - already processing")
            return False
            
        self.processing_users.add(user_id)
        try:
            # 1. Get Channel
            async with db.conn.execute("SELECT channel_id FROM digest_configs WHERE guild_id = ?", (guild_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return False
                channel_id = row['channel_id']

            channel = self.bot.get_channel(channel_id)
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except:
                    return False
            
            if not isinstance(channel, discord.TextChannel):
                return False

            # 2. Get Topics
            async with db.conn.execute("SELECT topic FROM digest_topics WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)) as cursor:
                # Deduplicate topics (case-insensitive) just in case
                raw_topics = [row['topic'] for row in await cursor.fetchall()]
                topics = sorted(list(set(raw_topics)), key=str.lower)
            
            if not topics:
                return False

            # 3. Create Thread
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            date_str = datetime.now().strftime("%Y-%m-%d")
            thread_name = f"Daily Digest for {user.display_name} - {date_str}"
            
            async with db.conn.execute("SELECT timezone FROM user_digest_settings WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)) as cursor:
                row = await cursor.fetchone()
                timezone_str = row['timezone'] if row else 'UTC'
            
            try:
                user_tz = ZoneInfo(timezone_str)
                current_hour = datetime.now(user_tz).hour
                if 5 <= current_hour < 12:
                    greeting = "Good morning"
                elif 12 <= current_hour < 18:
                    greeting = "Good afternoon"
                else:
                    greeting = "Good evening"
            except Exception:
                greeting = "Hello"

            try:
                start_msg = await channel.send(f"📰 **{greeting}, {user.mention}!** Here is your Daily Digest for {date_str}")
                thread = await start_msg.create_thread(name=thread_name, auto_archive_duration=1440)
            except Exception as e:
                logger.error(f"Failed to create thread: {e}")
                return False

            # 4. Process Topics
            for topic in topics:
                # A. Search
                search_results = await search_service.search(f"{topic} news today", count=3)
                
                # B. Summarize with AI
                if "No results found" in search_results:
                    await thread.send(f"**{topic}**\nNo recent news found.")
                    continue

                prompt = (
                    f"Topic: {topic}\n"
                    f"Search Results:\n{search_results}\n\n"
                    "Task: Write a short, engaging summary of the news for this topic. "
                    "Include 1-2 key links if available. "
                    "Format with Markdown. Do NOT include greetings (like Good morning)."
                )
                
                ai_response = await ai_service.generate_response(
                    system_prompt="You are a news anchor providing a daily digest. Jump straight into the news.",
                    user_message=prompt
                )
                
                content = ai_response.content
                
                # Chunking just in case
                if len(content) > 1900:
                    content = content[:1900] + "..."

                await thread.send(f"### {topic}\n{content}")

            # 5. Update last_sent_at
            await db.conn.execute("""
                UPDATE user_digest_settings 
                SET last_sent_at = CURRENT_TIMESTAMP 
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))
            await db.conn.commit()
            
            return True

        except Exception as e:
            logger.error(f"Failed to send digest to {user_id}: {e}")
            await db.log_error(e, {"context": "send_digest", "user_id": user_id})
            return False
        finally:
            self.processing_users.discard(user_id)

def setup(bot: commands.Bot):
    bot.add_cog(Digest(bot))
