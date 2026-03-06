import nextcord
from nextcord.ext import commands
from datetime import datetime, timezone

# === VARIABILI ID ===
TIROCINANTE_ROLE_ID = 1472996121717641399       
ID_PANEL_CANDIDATURE = 1472979512789827624      

# -------- CLASSE PULSANTI LOG (APPROVAZIONE) --------
class ApprovalView(nextcord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @nextcord.ui.button(label="✅ Approva", style=nextcord.ButtonStyle.green)
    async def approve(self, button: nextcord.ui.Button, btn_interaction: nextcord.Interaction):
        guild = btn_interaction.guild
        embed = btn_interaction.message.embeds[0]

        # Pulizia sicura dell'ID utente dalla menzione
        user_mention = embed.fields[2].value
        user_id = int(''.join(filter(str.isdigit, user_mention)))
        member = guild.get_member(user_id) or await guild.fetch_member(user_id)

        if not member:
            await btn_interaction.response.send_message("Utente non trovato nel server.", ephemeral=True)
            return

        nome_form = embed.fields[0].value
        nuovo_nome = f"Tir - {nome_form}"

        # Assegna ruolo
        role = guild.get_role(TIROCINANTE_ROLE_ID)
        if role:
            await member.add_roles(role)

        # Cambia nickname (gestisce errori di permessi)
        try:
            await member.edit(nick=nuovo_nome)
        except:
            print(f"Non ho potuto cambiare il nick a {member.name}")

        # Disabilita i tasti dopo l'azione
        for item in self.children:
            item.disabled = True
        await btn_interaction.message.edit(content=f"✅ Approvata da {btn_interaction.user.mention}", view=self)
        
        await btn_interaction.response.send_message(f"Candidatura di {member.mention} approvata!", ephemeral=True)

    @nextcord.ui.button(label="❌ Rifiuta", style=nextcord.ButtonStyle.red)
    async def reject(self, button: nextcord.ui.Button, btn_interaction: nextcord.Interaction):
        embed = btn_interaction.message.embeds[0]
        user_id = int(''.join(filter(str.isdigit, embed.fields[2].value)))
        member = btn_interaction.guild.get_member(user_id)

        if member:
            try:
                await member.send("❌ La tua candidatura all'Ospedale San Camillo è stata rifiutata.")
            except:
                pass

        for item in self.children:
            item.disabled = True
        await btn_interaction.message.edit(content=f"❌ Rifiutata da {btn_interaction.user.mention}", view=self)
        await btn_interaction.response.send_message("Candidatura rifiutata!", ephemeral=True)

# -------- CLASSE PULSANTI CANDIDATURA --------
class CandidaturaButton(nextcord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @nextcord.ui.button(label="✅ Candidati", style=nextcord.ButtonStyle.green)
    async def candidati(self, button: nextcord.ui.Button, btn_interaction: nextcord.Interaction):
        await btn_interaction.response.send_modal(FormCandidatura())

# --- CLASSE FORM CANDIDATURA ---
class FormCandidatura(nextcord.ui.Modal):
    def __init__(self):
        super().__init__("Compila la candidatura")
        self.nec = nextcord.ui.TextInput(label="Nome e Cognome", required=True, max_length=50)
        self.add_item(self.nec)
        self.cf = nextcord.ui.TextInput(label="Codice Fiscale / Nickname Minecraft", required=True)
        self.add_item(self.cf)
        self.pk = nextcord.ui.TextInput(label="Perché vuoi entrare?", required=True, style=nextcord.TextInputStyle.paragraph)
        self.add_item(self.pk)

    async def callback(self, interaction: nextcord.Interaction):
        target_channel = interaction.guild.get_channel(ID_PANEL_CANDIDATURE)
        
        embed = nextcord.Embed(
            title="Nuova candidatura!",
            color=nextcord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Nominativi", value=self.nec.value, inline=False)
        embed.add_field(name="Codice Fiscale", value=self.cf.value, inline=False)
        embed.add_field(name="Utente", value=interaction.user.mention, inline=False)
        embed.add_field(name="Motivazione", value=self.pk.value, inline=False)

        if target_channel:
            await target_channel.send(embed=embed, view=ApprovalView())
            await interaction.response.send_message("Candidatura inviata!", ephemeral=True)
        else:
            await interaction.response.send_message("Canale Log non trovato!", ephemeral=True)

# -------- CLASSE COG --------
class CandidaturaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @nextcord.slash_command(name="candidatura", description="Invia pannello candidatura", guild_ids=[1472706575641870336])
    async def candidatura(self, interaction: nextcord.Interaction):
        embed = nextcord.Embed(
            title="🏥 Candidature Ospedale San Camillo", 
            description="Compila il modulo cliccando il tasto qui sotto per sottoporre la tua richiesta allo staff.",
            color=nextcord.Color.red()
        )
        view = CandidaturaButton()
        await interaction.response.send_message("Pannello inviato!", ephemeral=True)
        await interaction.channel.send(embed=embed, view=view)

# -------- SETUP --------
def setup(bot):
    bot.add_cog(CandidaturaCog(bot))