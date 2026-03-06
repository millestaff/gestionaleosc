import nextcord
from nextcord.ext import commands
from datetime import datetime, timezone 

# === VARIABILI ID ===
CITTADINO_ROLE_ID = 1472931038836822016   # Ruolo Cittadino
WELCOME_CHANNEL_ID = 1472934014619877396  # Canale Benvenuto

class Benvenuto(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: nextcord.Member):
        # 1. Assegna ruolo automaticamente
        role = member.guild.get_role(CITTADINO_ROLE_ID)
        if role:
            try:
                await member.add_roles(role)
            except Exception as e:
                print(f"Errore assegnazione ruolo: {e}")
        
        # 2. Crea embed di benvenuto
        embed = nextcord.Embed(
            title="🎉 Benvenuto all'Ospedale San Camillo!",
            description=f"Ciao {member.mention}, siamo felici di averti con noi!",
            color=nextcord.Color.green()
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        # 3. Invia embed
        channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
        if channel:
            await channel.send(embed=embed)

# QUESTA FUNZIONE È OBBLIGATORIA PER CARICARE IL COG
def setup(bot):
    bot.add_cog(Benvenuto(bot))



# funzione necessaria per registrare il cog
def setup(bot):
    bot.add_cog(Benvenuto(bot))
