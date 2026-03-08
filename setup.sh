#!/bin/bash
# Eseguire da ~/gestionale (root del progetto)
set -e

echo "📁 Creando cartelle..."
mkdir -p templates/cittadini
mkdir -p routers

echo "📋 Copiando router cittadini..."
# Il router va in routers/cittadini.py

echo "⚙️ Aggiungendo CANALE_ANNUNCI_ID a config.py..."
# Aggiungi alla fine di config.py se non esiste
grep -q "CANALE_ANNUNCI_ID" config.py || echo '
CANALE_ANNUNCI_ID = os.getenv("CANALE_ANNUNCI_ID", "")
' >> config.py

echo "🔗 Aggiungendo router a main.py..."
# Controlla che non sia già incluso
grep -q "cittadini_router" main.py || python3 << 'PYEOF'
with open("main.py", "r") as f:
    content = f.read()

# Aggiungi import
old_import = "from routers.dashboard import router as dashboard_router"
new_import = old_import + "\nfrom routers.cittadini import router as cittadini_router"
content = content.replace(old_import, new_import)

# Aggiungi include_router
old_include = "app.include_router(dashboard_router)"
new_include = old_include + "\napp.include_router(cittadini_router)"
content = content.replace(old_include, new_include)

with open("main.py", "w") as f:
    f.write(content)
print("✅ main.py aggiornato")
PYEOF

echo "📊 Aggiungendo route candidature a dashboard.py..."
grep -q "candidature_page" routers/dashboard.py || python3 << 'PYEOF'
from datetime import datetime

routes = '''

# ─── CANDIDATURE MEDICO (dal portale cittadini) ───────────────────────────────

@router.get("/candidature", response_class=HTMLResponse)
async def candidature_page(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    from config import ROLE_PERMISSIONS
    import os
    candidature = await db["candidature_medico"].find().sort("timestamp", -1).to_list(100)
    role_ids = {
        "ROLE_TIROCINANTE": os.getenv("ROLE_TIROCINANTE", ""),
        "ROLE_MEDICO_BASE": os.getenv("ROLE_MEDICO_BASE", ""),
        "ROLE_INFERMIERE": os.getenv("ROLE_INFERMIERE", ""),
        "ROLE_MED_FORMAZIONE": os.getenv("ROLE_MED_FORMAZIONE", ""),
        "ROLE_SPECIALISTA": os.getenv("ROLE_SPECIALISTA", ""),
    }
    return templates.TemplateResponse("candidature.html", {
        "request": request,
        "user": user,
        "candidature": candidature,
        "role_ids": role_ids,
    })


@router.post("/candidature/approva")
async def candidatura_approva(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    from bson import ObjectId
    import nextcord
    from config import DISCORD_GUILD_ID, CANALE_ANNUNCI_ID
    form = await request.form()
    cand_id = form.get("candidatura_id")
    ruolo_id = form.get("ruolo_discord_id")

    candidatura = await db["candidature_medico"].find_one({"_id": ObjectId(cand_id)})
    if not candidatura:
        return JSONResponse({"status": "error", "detail": "Candidatura non trovata."})

    discord_id = candidatura["discord_id"]

    await db["candidature_medico"].update_one(
        {"_id": ObjectId(cand_id)},
        {"$set": {
            "stato": "approvata",
            "approvata_da": user["username"],
            "approvata_il": datetime.now().strftime("%d/%m/%Y %H:%M"),
        }}
    )

    try:
        from bot.cogs import get_bot
        bot = get_bot()
        guild = bot.get_guild(int(DISCORD_GUILD_ID)) if bot else None
        if guild and ruolo_id:
            try:
                member = guild.get_member(int(discord_id)) or await guild.fetch_member(int(discord_id))
            except Exception:
                member = None
            role = guild.get_role(int(ruolo_id))
            if member and role:
                await member.add_roles(role)
                embed = nextcord.Embed(
                    title="🏥 Candidatura Approvata!",
                    description=f"Congratulazioni! La tua candidatura è stata approvata da **{user[\'username\']}**.",
                    color=0x22c55e,
                    timestamp=datetime.utcnow(),
                )
                embed.add_field(name="👔 Ruolo Assegnato", value=role.name, inline=True)
                embed.add_field(name="🔗 Accesso", value="Puoi ora accedere al gestionale staff.", inline=False)
                embed.set_footer(text="Benvenuto nel team!")
                try:
                    await member.send(embed=embed)
                except Exception:
                    pass
                if CANALE_ANNUNCI_ID:
                    canale = bot.get_channel(int(CANALE_ANNUNCI_ID))
                    if canale:
                        embed_pub = nextcord.Embed(
                            title="👨‍⚕️ Nuovo Membro dello Staff!",
                            color=0x2563eb,
                            timestamp=datetime.utcnow(),
                        )
                        embed_pub.add_field(name="👤 Nuovo Membro", value=member.mention, inline=True)
                        embed_pub.add_field(name="🏷️ Ruolo", value=role.name, inline=True)
                        embed_pub.add_field(name="✅ Approvato da", value=user["username"], inline=True)
                        await canale.send(embed=embed_pub)
    except Exception as e:
        print(f"[CANDIDATURA] Errore: {e}")

    return JSONResponse({"status": "ok", "message": "Candidatura approvata e ruolo assegnato."})


@router.post("/candidature/rifiuta")
async def candidatura_rifiuta(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    from bson import ObjectId
    import nextcord
    from config import DISCORD_GUILD_ID
    form = await request.form()
    cand_id = form.get("candidatura_id")
    motivo = form.get("motivo", "Candidatura non idonea.")

    candidatura = await db["candidature_medico"].find_one({"_id": ObjectId(cand_id)})
    if not candidatura:
        return JSONResponse({"status": "error", "detail": "Candidatura non trovata."})

    await db["candidature_medico"].update_one(
        {"_id": ObjectId(cand_id)},
        {"$set": {
            "stato": "rifiutata",
            "approvata_da": user["username"],
            "approvata_il": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "motivo_rifiuto": motivo,
        }}
    )

    try:
        from bot.cogs import get_bot
        bot = get_bot()
        guild = bot.get_guild(int(DISCORD_GUILD_ID)) if bot else None
        if guild:
            try:
                member = guild.get_member(int(candidatura["discord_id"])) or await guild.fetch_member(int(candidatura["discord_id"]))
            except Exception:
                member = None
            if member:
                embed = nextcord.Embed(
                    title="🏥 Esito Candidatura",
                    color=0xef4444,
                    timestamp=datetime.utcnow(),
                )
                embed.add_field(name="📋 Esito", value="❌ Non approvata", inline=True)
                embed.add_field(name="📝 Motivazione", value=motivo, inline=False)
                embed.set_footer(text="Ospedale San Camillo")
                try:
                    await member.send(embed=embed)
                except Exception:
                    pass
    except Exception as e:
        print(f"[CANDIDATURA] Errore: {e}")

    return JSONResponse({"status": "ok", "message": "Candidatura rifiutata."})
'''

with open("routers/dashboard.py", "a") as f:
    f.write(routes)
print("✅ Route candidature aggiunte a dashboard.py")
PYEOF

echo ""
echo "✅ Setup completato! Ora:"
echo "1. Copia manualmente i file template in templates/cittadini/"
echo "2. Copia routers/cittadini.py"
echo "3. Aggiungi CANALE_ANNUNCI_ID su Render"
echo "4. git add . && git commit -m 'portale cittadini' && git push"
