import discord
from discord.ext import commands, tasks
from config import DISCORD_GUILD_ID
import asyncio

_bot_instance = None

def get_bot():
    return _bot_instance

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    global _bot_instance
    _bot_instance = bot
    print(f"[Bot] Connesso come {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"[Bot] {len(synced)} slash commands sincronizzati.")
    except Exception as e:
        print(f"[Bot] Errore sync: {e}")


@bot.tree.command(name="info", description="Mostra info sul gestionale")
async def info(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🏥 Ospedale San Camillo",
        description="Gestionale Interno",
        color=0xdc2626,
    )
    member = interaction.guild.get_member(interaction.user.id)
    if member:
        ruoli = [r.name for r in member.roles if r.name != "@everyone"]
        embed.add_field(name="👤 I tuoi ruoli", value=", ".join(ruoli) or "Nessuno", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.command(name="stato")
async def stato(ctx):
    embed = discord.Embed(
        title="🏥 Stato Gestionale",
        color=0xdc2626,
    )
    embed.add_field(name="✅ Web", value="Online", inline=True)
    embed.add_field(name="✅ Bot", value="Online", inline=True)
    await ctx.send(embed=embed)
