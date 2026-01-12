import discord
from discord.ext import commands
from typing import override
import logging
from ..services.db import db
from ..services.ai import ai_service
from ..services.emoji_manager import emoji_manager

logger = logging.getLogger("grok.settings")

class PersonaSelect(discord.ui.Select):
    def __init__(self, personas, author_id):
        self.author_id = author_id
        options = []
        for p in personas:
            # Truncate description to approx 7 words / 50 chars
            desc = p['description']
            if len(desc) > 50:
                desc = desc[:47] + "..."
            
            options.append(discord.SelectOption(
                label=p['name'],
                description=desc,
                value=str(p['id'])
            ))
        super().__init__(placeholder="Select a persona...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ You cannot control this menu.", ephemeral=True)
            return

        persona_id = int(self.values[0])
        name = next(opt.label for opt in self.options if opt.value == self.values[0])
        
        await db.conn.execute("""
            INSERT INTO guild_configs (guild_id, active_persona_id) 
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET active_persona_id = excluded.active_persona_id
        """, (interaction.guild.id, persona_id))
        await db.conn.commit()
        
        # Disable the dropdown
        self.disabled = True
        # Edit original message to show disabled view
        await interaction.response.edit_message(content=f"✅ Switched persona to **{name}**!", view=self.view)

class PersonaView(discord.ui.View):
    def __init__(self, personas, author_id):
        super().__init__()
        self.add_item(PersonaSelect(personas, author_id))

class PersonaDeleteSelect(discord.ui.Select):
    def __init__(self, personas, author_id):
        self.author_id = author_id
        options = []
        for p in personas:
            options.append(discord.SelectOption(
                label=p['name'],
                description=p['description'][:97] + '...' if len(p['description']) > 100 else p['description'],
                value=str(p['id'])
            ))
        super().__init__(placeholder="Select a persona to DELETE...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ You cannot control this menu.", ephemeral=True)
            return

        persona_id = int(self.values[0])
        name = next(opt.label for opt in self.options if opt.value == self.values[0])
        
        await db.conn.execute("DELETE FROM personas WHERE id = ?", (persona_id,))
        await db.conn.commit()
        
        self.disabled = True
        await interaction.response.edit_message(content=f"🗑️ Deleted persona **{name}**.", view=self.view)

class PersonaDeleteView(discord.ui.View):
    def __init__(self, personas, author_id):
        super().__init__()
        self.add_item(PersonaDeleteSelect(personas, author_id))


class PersonaModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Create New Persona")
        self.add_item(discord.ui.InputText(
            label="Describe the Persona",
            placeholder="e.g. Batman, or 'A sarcastic hacker'...",
            style=discord.InputTextStyle.paragraph,
            min_length=3,
            max_length=1000
        ))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_input = self.children[0].value
        
        try:
            # Generate Name, Description, and Prompt
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
                    name = line.replace("NAME:", "").strip()
                elif line.startswith("DESCRIPTION:"):
                    description = line.replace("DESCRIPTION:", "").strip()
                elif line.startswith("PROMPT:"):
                    prompt = line.replace("PROMPT:", "").strip()
            
            # Fallback if parsing fails
            if name == "Unknown":
                name = user_input.split()[0][:15]
                description = user_input[:50]
            
            # Check uniqueness
            async with db.conn.execute("SELECT 1 FROM personas WHERE name = ? COLLATE NOCASE", (name,)) as cursor:
                if await cursor.fetchone():
                    name = f"{name}_{interaction.user.discriminator}" # collision fallback

            await db.conn.execute("""
                INSERT INTO personas (name, description, system_prompt, is_global, created_by)
                VALUES (?, ?, ?, 0, ?)
            """, (name, description, prompt, interaction.user.id))
            await db.conn.commit()
            
            embed = discord.Embed(title="✨ Persona Created", color=discord.Color.green())
            embed.add_field(name="Name", value=name, inline=True)
            embed.add_field(name="Description", value=description, inline=True)
            embed.add_field(name="System Prompt", value=prompt, inline=False)
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Creation failed: {e}")

class Settings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    @override
    async def on_ready(self) -> None:
        logger.info(f'Cog {self.__class__.__name__} is ready.')

    persona = discord.SlashCommandGroup("persona", "Manage Grok's personality")

    @persona.command(name="switch", description="Switch the server's active persona")
    @discord.default_permissions(administrator=True)
    async def switch_persona(self, ctx: discord.ApplicationContext):
        # Fetch Standard first
        async with db.conn.execute("SELECT id, name, description FROM personas WHERE name = 'Standard'") as cursor:
            standard = await cursor.fetchall()
            
        # Fetch others alphabetical
        async with db.conn.execute("SELECT id, name, description FROM personas WHERE name != 'Standard' ORDER BY name") as cursor:
            others = await cursor.fetchall()
            
        personas = standard + others
            
        if not personas:
            await ctx.respond("No personas found!", ephemeral=False)
            return

        view = PersonaView(personas, ctx.author.id)
        await ctx.respond("🎭 **Choose a Persona**:", view=view)

    @persona.command(name="create", description="Create a new custom persona with AI assistance")
    @discord.default_permissions(administrator=True)
    async def create_persona(self, ctx: discord.ApplicationContext):
        modal = PersonaModal()
        await ctx.send_modal(modal)

    @persona.command(name="delete", description="Delete a custom persona")
    @discord.default_permissions(administrator=True)
    async def delete_persona(self, ctx: discord.ApplicationContext):
        # Fetch deletable personas (exclude Standard and globals if preferred, 
        # but for now assume admins can delete anything except 'Standard')
        async with db.conn.execute("SELECT id, name FROM personas WHERE name != 'Standard' ORDER BY name") as cursor:
            personas = await cursor.fetchall()
            
        if not personas:
            await ctx.respond("No custom personas found to delete.", ephemeral=False)
            return

        view = PersonaDeleteView(personas, ctx.author.id)
        await ctx.respond("🗑️ **Select a Persona to Delete**:", view=view, ephemeral=False)


    @persona.command(name="current", description="Show the current active persona")
    async def current_persona(self, ctx: discord.ApplicationContext):
        query = """
        SELECT p.name, p.description 
        FROM guild_configs g
        JOIN personas p ON g.active_persona_id = p.id
        WHERE g.guild_id = ?
        """
        async with db.conn.execute(query, (ctx.guild.id,)) as cursor:
            row = await cursor.fetchone()
        
        if row:
            await ctx.respond(f"🎭 Current Persona: **{row['name']}**\n*{row['description']}*")
        else:
            await ctx.respond("🎭 Current Persona: **Standard** (Default)")

    @discord.slash_command(name="analyze_emojis", description="Force re-analyze server emojis")
    @discord.default_permissions(administrator=True)
    async def analyze_emojis(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        try:
            count = await emoji_manager.analyze_guild_emojis(ctx.guild)
            await ctx.followup.send(f"✅ Analysis complete! Processed **{count}** new/updated emojis.")
        except Exception as e:
            await ctx.followup.send(f"❌ Analysis failed: {e}")

def setup(bot: commands.Bot) -> None:
    bot.add_cog(Settings(bot))
