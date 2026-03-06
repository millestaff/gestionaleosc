import nextcord
from nextcord.ext import commands
from nextcord.ui import View, Select, Modal, TextInput
import io
from datetime import datetime, timezone
from nextcord import ui


# --- CONFIGURAZIONE LOG ---
LOG_CHANNEL_ID = 1474178401429487828 # ID Canale i transcript

class TicketCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Funzione Utility per Transcript (Basata sul tuo codice precedente)
    async def generate_transcript(self, channel):
        messages = []
        async for msg in channel.history(limit=2000, oldest_first=True):
            messages.append(msg)
        
        if not messages:
            return None

        rows = []
        for m in messages:
            time = m.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            content = (m.content or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if m.attachments:
                for att in m.attachments:
                    content += f"<br><i style='color:#6366f1;'>[Allegato: {att.filename}]</i>"
            rows.append(f"<tr><td style='padding:8px; border:1px solid #444;'>{time}</td><td style='padding:8px; border:1px solid #444;'><b>{m.author}</b></td><td style='padding:8px; border:1px solid #444;'>{content}</td></tr>")

        html_content = f"<html><body style='font-family:sans-serif;background:#0f172a;color:#e5e7eb;padding:20px;'><h2>Transcript: #{channel.name}</h2><table style='width:100%;border-collapse:collapse;'>{''.join(rows)}</table></body></html>"
        return nextcord.File(io.BytesIO(html_content.encode("utf-8")), filename=f"transcript-{channel.name}.html")

    @nextcord.slash_command(name="ticket", description="Invia il pannello ticket", guild_ids=[1472706575641870336])
    async def ticketpanel(self, interaction: nextcord.Interaction):
        embed = nextcord.Embed(title="🎫 Supporto", description="Seleziona una categoria per aprire un ticket", color=nextcord.Color.blue())
        await interaction.response.send_message(embed=embed, view=TicketCategoryView(self.bot))

    @nextcord.slash_command(name="close", description="Chiude il ticket", guild_ids=[1472706575641870336])
    async def close_ticket(self, interaction: nextcord.Interaction):
        if not interaction.channel.name.startswith("ticket-"):
            return await interaction.response.send_message("❌ Questo comando può essere usato solo nei ticket", ephemeral=True)

        await interaction.response.send_message("💾 chiusura in corso...")
        
        # Generazione e Invio Transcript
        transcript_file = await self.generate_transcript(interaction.channel)
        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)

        if log_channel and transcript_file:
            await log_channel.send(
                content=f"📑 **Ticket Chiuso**\n**Canale:** {interaction.channel.name}\n**Chiuso da:** {interaction.user.mention}",
                file=transcript_file
            )
        
        await interaction.channel.delete()

    @nextcord.slash_command(name="claim", description="Prendi in carico il ticket", guild_ids=[1472706575641870336])
    async def claim_ticket(self, interaction: nextcord.Interaction):
        if not interaction.channel.name.startswith("ticket-"):
            return await interaction.response.send_message("Solo nei ticket!", ephemeral=True)
        
        embed = nextcord.Embed(description=f"🙋 Ticket claimato da {interaction.user.mention}\n", color=nextcord.Color.orange())
        await interaction.response.send_message(embed=embed)

    @nextcord.slash_command(name="add", description="Aggiunge un utente al ticket", guild_ids=[1472706575641870336])
    async def add_user(self, interaction: nextcord.Interaction, user: nextcord.Member):
        if not interaction.channel.name.startswith("ticket-"): return
        await interaction.channel.set_permissions(user, view_channel=True, send_messages=True, read_message_history=True)
        await interaction.response.send_message(f"{user.mention} aggiunto.")

# --- UI COMPONENTS (Dallo script precedente) ---

class TicketCategoryView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.add_item(CategorySelect(bot))

class CategorySelect(Select):
    def __init__(self, bot):
        self.bot = bot
        options = [
            nextcord.SelectOption(label="Dirigenza", value="dirigenza", emoji="📁"),
            nextcord.SelectOption(label="Segnalazione", value="segnalazione", emoji="⚠️"),
            nextcord.SelectOption(label="Specializzazione", value="specializzazione", emoji="🧪"),
            nextcord.SelectOption(label="Altro", value="altro", emoji="🛠️"),
        ]
        super().__init__(placeholder="Seleziona la categoria...", options=options)

    async def callback(self, interaction: nextcord.Interaction):
        await interaction.response.send_modal(TicketModal(self.bot, self.values[0]))

class TicketModal(Modal):
    def __init__(self, bot, categoria):
        super().__init__(title=f"Ticket - {categoria}")
        
        self.bot = bot
        # QUESTA RIGA È FONDAMENTALE: salva il valore nell'oggetto
        self.categoria = categoria 
        
        self.nomecognome = ui.TextInput(
            label="Nome e cognome",
            placeholder="Inserisci un nome e cognome",
            required=True
        )
        self.add_item(self.nomecognome)
        
        self.cf = ui.TextInput(
            label="Codice Fiscale",
            placeholder="Inserisci il tuo Nick di Minecraft",
            required=True
        )
        self.add_item(self.cf)
        
        self.motivo = ui.TextInput(
            label="Inserisci il motivo",
            placeholder="Inserisci un breve riassunto",
            required=True
        )
        self.add_item(self.motivo)

    async def callback(self, interaction: nextcord.Interaction):
        guild = interaction.guild
        cat = nextcord.utils.get(guild.categories, name="TICKET") or await guild.create_category("TICKET")
        
        # Permessi: l'utente vede il canale, @everyone no
        overwrites = {
            guild.default_role: nextcord.PermissionOverwrite(view_channel=False),
            interaction.user: nextcord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        
        channel = await guild.create_text_channel(name=f"ticket-{interaction.user.name}", category=cat, overwrites=overwrites)
        
        embed = nextcord.Embed(title="Ticket Aperto", color=nextcord.Color.green())
        embed.add_field(name="Utente", value=interaction.user.mention)
        embed.add_field(name="Categoria", value=self.categoria)
        embed.add_field(name="", value="", inline=True)
        embed.add_field(name="Nome e Cognome", value=self.nomecognome.value, inline=True)
        embed.add_field(name="Codice Fiscale", value=self.cf.value, inline=True)
        embed.add_field(name="Riassunto", value=self.motivo.value, inline=False)
        
        await channel.send(content=f"{interaction.user.mention} Benvenuto nel supporto!", embed=embed)
        await interaction.response.send_message(f"Ticket creato: {channel.mention}", ephemeral=True)

def setup(bot):
    bot.add_cog(TicketCog(bot))
