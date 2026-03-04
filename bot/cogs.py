import discord
from discord.ext import commands
from config import DISCORD_GUILD_ID, ROLE_PERMISSIONS, RUOLI_DIRIGENZA, RUOLI_REPARTO
from datetime import datetime

_bot_instance = None

def get_bot():
    return _bot_instance

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


def calcola_permesso(role_ids: list[str]) -> int:
    level = 0
    for rid in role_ids:
        level = max(level, ROLE_PERMISSIONS.get(str(rid), 0))
    return level


def calcola_categoria(ruolo: str) -> str:
    if ruolo in RUOLI_DIRIGENZA:
        return "dirigenza"
    elif ruolo in RUOLI_REPARTO:
        return "reparto"
    return "tirocinio"


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


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    """Aggiorna il DB quando i ruoli di un membro cambiano."""
    if before.roles == after.roles:
        return

    from database import get_db
    db = get_db()

    discord_id = str(after.id)
    role_ids = [str(r.id) for r in after.roles]
    nuovo_permesso = calcola_permesso(role_ids)

    # Trova il nome del ruolo principale
    ruolo_nome = "Medico Tirocinante"
    for r in after.roles:
        if str(r.id) in ROLE_PERMISSIONS:
            ruolo_nome = r.name
            break

    categoria = calcola_categoria(ruolo_nome)

    dipendente = await db["dipendenti"].find_one({"discord_id": discord_id})

    if dipendente:
        await db["dipendenti"].update_one(
            {"discord_id": discord_id},
            {"$set": {
                "ruolo":      ruolo_nome,
                "categoria":  categoria,
                "permission": nuovo_permesso,
                "role_ids":   role_ids,
                "aggiornato_il": datetime.now().strftime("%d/%m/%Y %H:%M"),
            }}
        )
        print(f"[Bot] Aggiornato {after.name}: ruolo={ruolo_nome}, permesso={nuovo_permesso}")

        # Notifica il membro del cambio ruolo
        try:
            embed = discord.Embed(
                title="🏥 Ospedale San Camillo — Ruolo Aggiornato",
                color=0xdc2626,
                timestamp=datetime.utcnow(),
            )
            embed.add_field(name="👤 Account", value=after.mention, inline=False)
            embed.add_field(name="🏷️ Nuovo Ruolo", value=ruolo_nome, inline=True)
            embed.add_field(name="🔑 Livello Accesso", value=str(nuovo_permesso), inline=True)
            embed.set_footer(text="Il tuo accesso al gestionale è stato aggiornato automaticamente.")
            await after.send(embed=embed)
        except Exception:
            pass
    else:
        print(f"[Bot] Membro {after.name} non trovato nel DB.")


@bot.tree.command(name="info", description="Mostra info sul tuo accesso al gestionale")
async def info(interaction: discord.Interaction):
    from database import get_db
    db = get_db()
    discord_id = str(interaction.user.id)
    dip = await db["dipendenti"].find_one({"discord_id": discord_id})
    embed = discord.Embed(title="🏥 Ospedale San Camillo", color=0xdc2626)
    if dip:
        embed.add_field(name="👤 Nome", value=f"{dip.get('nome','')} {dip.get('cognome','')}", inline=True)
        embed.add_field(name="🏷️ Ruolo", value=dip.get("ruolo","—"), inline=True)
        embed.add_field(name="✅ Approvato", value="Sì" if dip.get("approvato") else "In attesa", inline=True)
    else:
        embed.description = "Non sei ancora registrato nel gestionale."
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.command(name="stato")
async def stato(ctx):
    embed = discord.Embed(title="🏥 Stato Gestionale", color=0xdc2626)
    embed.add_field(name="✅ Web", value="Online", inline=True)
    embed.add_field(name="✅ Bot", value="Online", inline=True)
    await ctx.send(embed=embed)
