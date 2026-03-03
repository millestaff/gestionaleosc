import discord
from discord.ext import commands, tasks
from config import DISCORD_GUILD_ID


class SyncCog(commands.Cog):

    def __init__(self, bot: commands.Bot, db):
        self.bot = bot
        self.db = db
        self.sync_roles_task.start()

    def cog_unload(self):
        self.sync_roles_task.cancel()

    @tasks.loop(minutes=10)
    async def sync_roles_task(self):
        await self._sync_roles()

    @sync_roles_task.before_loop
    async def before_sync(self):
        await self.bot.wait_until_ready()

    async def _sync_roles(self):
        guild = self.bot.get_guild(DISCORD_GUILD_ID)
        if not guild:
            return
        ops = [
            {"updateOne": {
                "filter": {"role_id": str(role.id)},
                "update": {"$set": {"role_id": str(role.id), "name": role.name}},
                "upsert": True,
            }}
            for role in guild.roles
        ]
        if ops:
            await self.db["guild_roles"].bulk_write(ops)
        print(f"[Bot] Sincronizzati {len(ops)} ruoli del server.")

    @commands.command(name="stato")
    async def stato(self, ctx: commands.Context):
        embed = discord.Embed(
            title="🟢 Gestionale Online",
            description="Il sistema di gestione è operativo.",
            color=0x2563EB,
        )
        embed.set_footer(text="Gestionale Polizia FiveM")
        await ctx.send(embed=embed)

    @discord.app_commands.command(name="info", description="Info sull'agente")
    async def info_slash(self, interaction: discord.Interaction):
        member = interaction.user
        roles = [r.name for r in member.roles if r.name != "@everyone"]
        embed = discord.Embed(title=f"👮 {member.display_name}", color=0x2563EB)
        embed.add_field(name="Ruoli", value=", ".join(roles) or "Nessuno")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup_bot(bot: commands.Bot, db):
    await bot.add_cog(SyncCog(bot, db))
