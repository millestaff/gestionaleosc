import nextcord
from nextcord.ext import commands
from datetime import datetime, timezone

# 1. Sposta la View fuori o dentro il Cog (qui è fuori per comodità)
class InfoButton(nextcord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @nextcord.ui.button(label="🥇 Gerarchia", style=nextcord.ButtonStyle.green)
    async def gerarchia(self, button: nextcord.ui.Button, btn_interaction: nextcord.Interaction):
        embed = nextcord.Embed(
            title="🥇 Gerarchia",
            description="Ecco la struttura dell'Ospedale:",
            color=nextcord.Color.gold()
        )
        embed.add_field(name="💼 Dirigenza", value="Direttore\nResponsabili (Assunzione e Formazione, Farmacia, Amministrazione e Sanità)", inline=False)
        embed.add_field(name="💉 Reparto", value="Primario\nVice Primario\nSpecialista\nMFS", inline=False)
        embed.add_field(name="🩺 Tirocinio", value="Medico di Base\nMedico Assistente (Infermiere)\nMedico Tirocinante", inline=False)
        await btn_interaction.response.send_message(embed=embed, ephemeral=True)

    @nextcord.ui.button(label="🚧 prossimamente", style=nextcord.ButtonStyle.secondary)
    async def prossimamente(self, button: nextcord.ui.Button, btn_interaction: nextcord.Interaction):
        await btn_interaction.response.send_message("🚧 Presto in arrivo!", ephemeral=True)

# 2. Definisci la classe del Cog
class InfoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 3. Usa il decoratore corretto per i comandi Slash
    @nextcord.slash_command(name="info", description="Invia il pannello informativo", guild_ids=[1472706575641870336])
    async def info(self, interaction: nextcord.Interaction): # Aggiunto self
        embed = nextcord.Embed(title="Info OSC", color=nextcord.Color.red())
        embed.add_field(name="OSC", value="Ospedale della città di Estovia", inline=False)
        
        # Risposta all'interazione
        await interaction.response.send_message("Pannello info inviato!", ephemeral=True)
        # Invio dell'embed nel canale con la View
        await interaction.channel.send(embed=embed, view=InfoButton())

# 4. Funzione setup fondamentale per caricare il modulo
def setup(bot):
    bot.add_cog(InfoCog(bot))

