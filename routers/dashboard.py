from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
from auth import get_current_user, require_permission, require_write
from database import get_db
from config import TUTTI_RUOLI, RUOLI_DIRIGENZA, RUOLI_REPARTO, RUOLI_TIROCINIO

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
templates = Jinja2Templates(directory="templates")

CATEGORIE_BASE = ["cartella_clinica", "referto"]
CATEGORIE_TUTTE = ["cartella_clinica", "referto", "verbale", "rapporto", "regolamento", "modulo", "protocollo", "altro"]


# ── DASHBOARD ─────────────────────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    discord_id = user.get("discord_id")
    richiami_personali = await db["richiami"].count_documents({
        "discord_id": discord_id, "status": "attivo"
    })
    stats = {
        "dipendenti_totali": await db["dipendenti"].count_documents({"approvato": True}),
        "pazienti_attivi":   await db["pazienti"].count_documents({"status": "ricoverato"}),
        "documenti":         await db["documenti"].count_documents({}),
        "richiami_attivi":   await db["richiami"].count_documents({"status": "attivo"}),
        "segnalazioni":      await db["segnalazioni"].count_documents({"status": "aperta"}),
        "comunicati":        await db["comunicati"].count_documents({}),
        "richiami_personali": richiami_personali,
        "in_attesa":         await db["dipendenti"].count_documents({"approvato": False}) if user.get("permission", 0) >= 100 else 0,
    }
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user,
        "stats": stats, "active_section": "dashboard",
    })


# ── DIPENDENTI ────────────────────────────────────────────────────────────────
@router.get("/dipendenti/dirigenza", response_class=HTMLResponse)
async def dipendenti_dirigenza(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    lista = await db["dipendenti"].find({"categoria": "dirigenza", "approvato": True}).to_list(100)
    return templates.TemplateResponse("dipendenti.html", {
        "request": request, "user": user,
        "dipendenti": lista, "categoria": "Dirigenza",
        "ruoli": RUOLI_DIRIGENZA, "active_section": "dirigenza",
    })

@router.get("/dipendenti/reparto", response_class=HTMLResponse)
async def dipendenti_reparto(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    lista = await db["dipendenti"].find({"categoria": "reparto", "approvato": True}).to_list(100)
    return templates.TemplateResponse("dipendenti.html", {
        "request": request, "user": user,
        "dipendenti": lista, "categoria": "Reparto",
        "ruoli": RUOLI_REPARTO, "active_section": "reparto",
    })

@router.get("/dipendenti/tirocinio", response_class=HTMLResponse)
async def dipendenti_tirocinio(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    lista = await db["dipendenti"].find({"categoria": "tirocinio", "approvato": True}).to_list(100)
    return templates.TemplateResponse("dipendenti.html", {
        "request": request, "user": user,
        "dipendenti": lista, "categoria": "Tirocinio",
        "ruoli": RUOLI_TIROCINIO, "active_section": "tirocinio",
    })

@router.get("/dipendenti/add", response_class=HTMLResponse)
async def dipendenti_add_page(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    return templates.TemplateResponse("dipendenti_add.html", {
        "request": request, "user": user,
        "ruoli_dirigenza": RUOLI_DIRIGENZA,
        "ruoli_reparto": RUOLI_REPARTO,
        "ruoli_tirocinio": RUOLI_TIROCINIO,
        "active_section": "add_dipendente",
    })

@router.post("/dipendenti/add")
async def add_dipendente(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    form = await request.form()
    ruolo = form.get("ruolo", "")
    if ruolo in RUOLI_DIRIGENZA:
        categoria = "dirigenza"
    elif ruolo in RUOLI_REPARTO:
        categoria = "reparto"
    else:
        categoria = "tirocinio"
    await db["dipendenti"].insert_one({
        "nome":        form.get("nome"),
        "cognome":     form.get("cognome"),
        "discord_id":  form.get("discord_id"),
        "ruolo":       ruolo,
        "categoria":   categoria,
        "badge":       form.get("badge"),
        "stato":       form.get("stato", "in servizio"),
        "approvato":   True,
        "sanzioni":    [],
        "note":        form.get("note", ""),
        "added_by":    user["username"],
        "timestamp":   datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
    return {"status": "ok", "message": "Dipendente aggiunto con successo."}

@router.post("/dipendenti/aggiorna-stato")
async def aggiorna_stato_dipendente(request: Request, user: dict = Depends(require_permission(50)), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    await db["dipendenti"].update_one(
        {"_id": ObjectId(form.get("dipendente_id"))},
        {"$set": {"stato": form.get("stato")}}
    )
    return {"status": "ok", "message": "Stato aggiornato."}


# ── PAZIENTI ──────────────────────────────────────────────────────────────────
@router.get("/pazienti", response_class=HTMLResponse)
async def pazienti(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    lista = await db["pazienti"].find({"archiviato": {"$ne": True}}).sort("timestamp", -1).to_list(100)
    cittadini = await db["cittadini"].find().sort("registrato_il", -1).to_list(200)
    dipendenti = await db["dipendenti"].find({"approvato": True}).to_list(100)
    visite = await db["prenotazioni_visite"].find().sort("timestamp", -1).to_list(200)
    return templates.TemplateResponse("pazienti.html", {
        "request": request, "user": user,
        "pazienti": lista, "cittadini": cittadini,
        "dipendenti": dipendenti, "visite": visite,
        "active_section": "pazienti",
    })

@router.post("/pazienti/add")
async def add_paziente(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    form = await request.form()
    await db["pazienti"].insert_one({
        "nome":           form.get("nome"),
        "cognome":        form.get("cognome"),
        "eta":            form.get("eta"),
        "diagnosi":       form.get("diagnosi"),
        "medico_ref":     form.get("medico_ref"),
        "status":         form.get("status", "ricoverato"),
        "note":           form.get("note", ""),
        "registered_by":  user["username"],
        "timestamp":      datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
    return {"status": "ok", "message": "Paziente registrato."}

@router.post("/pazienti/aggiorna-status")
async def aggiorna_status_paziente(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    await db["pazienti"].update_one(
        {"_id": ObjectId(form.get("paziente_id"))},
        {"$set": {"status": form.get("status")}}
    )
    return {"status": "ok", "message": "Status paziente aggiornato."}


# ── DOCUMENTI ─────────────────────────────────────────────────────────────────
@router.get("/documenti", response_class=HTMLResponse)
async def documenti(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    categoria = request.query_params.get("categoria", "tutti")
    permission = user.get("permission", 0)
    categorie_disponibili = CATEGORIE_TUTTE if permission >= 50 else CATEGORIE_BASE
    if categoria != "tutti" and categoria not in categorie_disponibili:
        categoria = "tutti"
    query = {} if categoria == "tutti" else {"categoria": categoria}
    if permission < 50:
        query["categoria"] = {"$in": CATEGORIE_BASE}
    docs = await db["documenti"].find(query).sort("timestamp", -1).to_list(100)
    return templates.TemplateResponse("documenti.html", {
        "request": request, "user": user,
        "docs": docs, "categoria_attiva": categoria,
        "categorie_disponibili": categorie_disponibili,
        "active_section": "documenti",
    })

@router.post("/documenti/add")
async def add_documento(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    form = await request.form()
    categoria = form.get("categoria")
    permission = user.get("permission", 0)
    if permission < 50 and categoria not in CATEGORIE_BASE:
        return {"status": "error", "message": "Non hai i permessi per inserire questa categoria."}
    await db["documenti"].insert_one({
        "titolo":      form.get("titolo"),
        "categoria":   categoria,
        "contenuto":   form.get("contenuto"),
        "riferimento": form.get("riferimento", ""),
        "author":      user["username"],
        "timestamp":   datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
    return {"status": "ok", "message": "Documento aggiunto."}


# ── RICHIAMI ──────────────────────────────────────────────────────────────────
@router.get("/richiami", response_class=HTMLResponse)
async def richiami(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    permission = user.get("permission", 0)
    discord_id = user.get("discord_id")
    dipendenti = await db["dipendenti"].find({"approvato": True}).to_list(100)

    if permission >= 50:
        lista = await db["richiami"].find().sort("timestamp", -1).to_list(100)
    else:
        lista = await db["richiami"].find({"discord_id": discord_id}).sort("timestamp", -1).to_list(100)

    return templates.TemplateResponse("richiami.html", {
        "request": request, "user": user,
        "richiami": lista, "dipendenti": dipendenti,
        "active_section": "richiami",
    })

@router.post("/richiami/add")
async def add_richiamo(request: Request, user: dict = Depends(require_permission(50)), db=Depends(get_db)):
    form = await request.form()
    richiamo = {
        "destinatario":  form.get("destinatario"),
        "discord_id":    form.get("discord_id", ""),
        "tipo":          form.get("tipo"),
        "motivazione":   form.get("motivazione"),
        "emesso_da":     user["username"],
        "status":        "attivo",
        "timestamp":     datetime.now().strftime("%d/%m/%Y %H:%M"),
    }
    await db["richiami"].insert_one(richiamo)
    await db["dipendenti"].update_one(
        {"discord_id": form.get("discord_id")},
        {"$push": {"sanzioni": {
            "tipo":      form.get("tipo"),
            "motivo":    form.get("motivazione"),
            "data":      datetime.now().strftime("%d/%m/%Y %H:%M"),
            "emesso_da": user["username"],
        }}}
    )
    return {"status": "ok", "message": "Richiamo assegnato."}

@router.post("/richiami/chiudi")
async def chiudi_richiamo(request: Request, user: dict = Depends(require_permission(50)), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    await db["richiami"].update_one(
        {"_id": ObjectId(form.get("richiamo_id"))},
        {"$set": {"status": "chiuso"}}
    )
    return {"status": "ok", "message": "Richiamo chiuso."}

@router.post("/richiami/elimina")
async def elimina_richiamo(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    await db["richiami"].delete_one({"_id": ObjectId(form.get("richiamo_id"))})
    return {"status": "ok", "message": "Richiamo eliminato."}


# ── SEGNALAZIONI ──────────────────────────────────────────────────────────────
@router.get("/segnalazioni", response_class=HTMLResponse)
async def segnalazioni(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    items = await db["segnalazioni"].find().sort("timestamp", -1).to_list(50)
    return templates.TemplateResponse("segnalazioni.html", {
        "request": request, "user": user,
        "items": items, "active_section": "segnalazioni",
    })

@router.post("/segnalazioni/add")
async def add_segnalazione(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    form = await request.form()
    await db["segnalazioni"].insert_one({
        "tipo":        form.get("tipo"),
        "priorita":    form.get("priorita"),
        "reparto":     form.get("reparto"),
        "descrizione": form.get("descrizione"),
        "author":      user["username"],
        "status":      "aperta",
        "timestamp":   datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
    return {"status": "ok", "message": "Segnalazione inviata."}

@router.post("/segnalazioni/aggiorna")
async def aggiorna_segnalazione(request: Request, user: dict = Depends(require_permission(50)), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    await db["segnalazioni"].update_one(
        {"_id": ObjectId(form.get("segnalazione_id"))},
        {"$set": {"status": form.get("status")}}
    )
    return {"status": "ok", "message": "Segnalazione aggiornata."}


# ── COMUNICATI ────────────────────────────────────────────────────────────────
@router.get("/comunicati", response_class=HTMLResponse)
async def comunicati(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    lista = await db["comunicati"].find().sort("timestamp", -1).to_list(50)
    return templates.TemplateResponse("comunicati.html", {
        "request": request, "user": user,
        "comunicati": lista, "active_section": "comunicati",
    })

@router.post("/comunicati/add")
async def add_comunicato(request: Request, user: dict = Depends(require_permission(50)), db=Depends(get_db)):
    form = await request.form()
    await db["comunicati"].insert_one({
        "titolo":      form.get("titolo"),
        "contenuto":   form.get("contenuto"),
        "priority":    form.get("priority"),
        "destinatari": form.get("destinatari"),
        "author":      user["username"],
        "timestamp":   datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
    return {"status": "ok", "message": "Comunicato pubblicato."}


# ── PEC ───────────────────────────────────────────────────────────────────────
@router.get("/pec", response_class=HTMLResponse)
async def pec(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    # Dirigenza vede tutto, altri vedono solo le proprie
    if user.get("permission", 0) >= 50:
        pec_list = await db["pec"].find().sort("timestamp", -1).to_list(200)
    else:
        pec_list = await db["pec"].find({
            "$or": [
                {"mittente": user["username"]},
                {"mittente_id": user["discord_id"]},
                {"destinatario": f"dipendente:{user['discord_id']}"},
                {"destinatario": f"paziente:{user['discord_id']}"},
                {"destinatario": f"cittadino:{user['discord_id']}"},
                {"destinatario": {"$regex": "reparto:"}},
            ]
        }).sort("timestamp", -1).to_list(100)
    dipendenti = await db["dipendenti"].find({"approvato": True}).to_list(100)
    cittadini = await db["cittadini"].find().sort("username", 1).to_list(200)
    return templates.TemplateResponse("pec.html", {
        "request": request, "user": user,
        "pec_list": pec_list, "dipendenti": dipendenti,
        "cittadini": cittadini,
        "active_section": "pec",
    })

@router.post("/pec/send")
async def send_pec(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    from bot.cogs import get_bot
    form = await request.form()
    destinatario = form.get("destinatario")
    oggetto = form.get("oggetto")
    corpo = form.get("corpo")
    await db["pec"].insert_one({
        "destinatario": destinatario,
        "oggetto":      oggetto,
        "corpo":        corpo,
        "priorita":     form.get("priorita", "normale"),
        "mittente":     user["username"],
        "mittente_id":  user["discord_id"],
        "stato":        "inviata",
        "timestamp":    datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
    # Notifica DM al destinatario
    try:
        bot = get_bot()
        if bot and destinatario.startswith("paziente:") or destinatario.startswith("cittadino:"):
            discord_id = int(destinatario.split(":")[1])
            dest_user = await bot.fetch_user(discord_id)
            if dest_user:
                await dest_user.send(
                    f"📨 **Nuova PEC ricevuta** dall'Ospedale San Camillo\n"
                    f"**Oggetto:** {oggetto}\n"
                    f"**Da:** {user['username']}\n"
                    f"Accedi al portale per leggere il messaggio completo."
                )
        elif destinatario and ":" not in destinatario:
            # Destinatario è uno staff — cerca il suo discord_id
            dest = await db["dipendenti"].find_one({"username": destinatario})
            if dest and dest.get("discord_id"):
                discord_id = int(dest["discord_id"])
                dest_user = await bot.fetch_user(discord_id)
                if dest_user:
                    await dest_user.send(
                        f"📨 **Nuova PEC ricevuta**\n"
                        f"**Oggetto:** {oggetto}\n"
                        f"**Da:** {user['username']}\n"
                        f"Accedi al gestionale per leggere il messaggio completo."
                    )
    except Exception as e:
        print(f"[PEC] Errore notifica DM: {e}")
    return {"status": "ok", "message": "PEC inviata con successo."}


# ── STORICO ───────────────────────────────────────────────────────────────────
@router.get("/storico", response_class=HTMLResponse)
async def storico(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    actions = await db["actions"].find().sort("timestamp", -1).to_list(50)
    return templates.TemplateResponse("storico.html", {
        "request": request, "user": user,
        "actions": actions, "active_section": "storico",
    })


# ── STATISTICHE ───────────────────────────────────────────────────────────────
@router.get("/statistiche", response_class=HTMLResponse)
async def statistiche(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    stats = {
        "dipendenti_totali":   await db["dipendenti"].count_documents({"approvato": True}),
        "dirigenza":           await db["dipendenti"].count_documents({"categoria": "dirigenza", "approvato": True}),
        "reparto":             await db["dipendenti"].count_documents({"categoria": "reparto", "approvato": True}),
        "tirocinio":           await db["dipendenti"].count_documents({"categoria": "tirocinio", "approvato": True}),
        "pazienti_totali":     await db["pazienti"].count_documents({}),
        "pazienti_ricoverati": await db["pazienti"].count_documents({"status": "ricoverato"}),
        "pazienti_dimessi":    await db["pazienti"].count_documents({"status": "dimesso"}),
        "richiami_attivi":     await db["richiami"].count_documents({"status": "attivo"}),
        "richiami_chiusi":     await db["richiami"].count_documents({"status": "chiuso"}),
        "segnalazioni_aperte": await db["segnalazioni"].count_documents({"status": "aperta"}),
        "documenti_totali":    await db["documenti"].count_documents({}),
    }
    return templates.TemplateResponse("statistiche.html", {
        "request": request, "user": user,
        "stats": stats, "active_section": "statistiche",
    })


# ── GESTIONE UTENTI ───────────────────────────────────────────────────────────
@router.get("/utenti", response_class=HTMLResponse)
async def utenti(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    approvati = await db["dipendenti"].find({"approvato": True}).to_list(100)
    in_attesa = await db["dipendenti"].find({"approvato": False}).to_list(100)
    return templates.TemplateResponse("utenti.html", {
        "request": request, "user": user,
        "dipendenti": approvati,
        "in_attesa": in_attesa,
        "active_section": "utenti",
        "tutti_ruoli": TUTTI_RUOLI,
    })

@router.post("/utenti/approva")
async def approva_utente(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    await db["dipendenti"].update_one(
        {"_id": ObjectId(form.get("dipendente_id"))},
        {"$set": {
            "approvato": True,
            "approvato_da": user["username"],
            "approvato_il": datetime.now().strftime("%d/%m/%Y %H:%M"),
        }}
    )
    return {"status": "ok", "message": "Utente approvato."}

@router.post("/utenti/rifiuta")
async def rifiuta_utente(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    await db["dipendenti"].delete_one({"_id": ObjectId(form.get("dipendente_id"))})
    return {"status": "ok", "message": "Utente rifiutato e rimosso."}

@router.post("/utenti/aggiorna-ruolo")
async def aggiorna_ruolo(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    ruolo = form.get("ruolo")
    if ruolo in RUOLI_DIRIGENZA:
        categoria = "dirigenza"
    elif ruolo in RUOLI_REPARTO:
        categoria = "reparto"
    else:
        categoria = "tirocinio"
    await db["dipendenti"].update_one(
        {"_id": ObjectId(form.get("dipendente_id"))},
        {"$set": {"ruolo": ruolo, "categoria": categoria}}
    )
    return {"status": "ok", "message": "Ruolo aggiornato."}

@router.post("/utenti/elimina")
async def elimina_dipendente(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    await db["dipendenti"].delete_one({"_id": ObjectId(form.get("dipendente_id"))})
    return {"status": "ok", "message": "Dipendente rimosso."}


@router.post("/utenti/aggiorna-dettagli")
async def aggiorna_dettagli(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    await db["dipendenti"].update_one(
        {"_id": ObjectId(form.get("dipendente_id"))},
        {"$set": {
            "nome":    form.get("nome"),
            "cognome": form.get("cognome"),
            "badge":   form.get("badge"),
        }}
    )
    return {"status": "ok", "message": "Dettagli aggiornati."}


@router.post("/pec/elimina")
async def elimina_pec(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    await db["pec"].delete_one({"_id": ObjectId(form.get("pec_id"))})
    return {"status": "ok", "message": "PEC eliminata."}


@router.post("/documenti/elimina")
async def elimina_documento(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    await db["documenti"].delete_one({"_id": ObjectId(form.get("documento_id"))})
    return {"status": "ok", "message": "Documento eliminato."}


@router.post("/segnalazioni/elimina")
async def elimina_segnalazione(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    await db["segnalazioni"].delete_one({"_id": ObjectId(form.get("segnalazione_id"))})
    return {"status": "ok", "message": "Segnalazione eliminata."}


@router.post("/comunicati/elimina")
async def elimina_comunicato(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    await db["comunicati"].delete_one({"_id": ObjectId(form.get("comunicato_id"))})
    return {"status": "ok", "message": "Comunicato eliminato."}


@router.post("/pazienti/elimina")
async def elimina_paziente(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    await db["pazienti"].delete_one({"_id": ObjectId(form.get("paziente_id"))})
    return {"status": "ok", "message": "Paziente eliminato."}


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
                    description=f"Congratulazioni! La tua candidatura è stata approvata da **{user['username']}**.",
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


@router.get("/corsi", response_class=HTMLResponse)
async def corsi_page(request: Request, user: dict = Depends(require_permission(10)), db=Depends(get_db)):
    corsi = await db["corsi"].find().sort("timestamp", -1).to_list(100)
    for corso in corsi:
        corso_id = str(corso["_id"])
        partecipanti = await db["prenotazioni_corsi"].find({"corso_id": corso_id}).to_list(100)
        corso["partecipanti"] = partecipanti
        corso["iscritti"] = len([p for p in partecipanti if p.get("stato") != "annullata"])
    return templates.TemplateResponse("corsi.html", {
        "request": request,
        "user": user,
        "corsi": corsi,
    })


@router.post("/corsi/crea")
async def corso_crea(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    from datetime import datetime
    form = await request.form()
    tipo = form.get("tipo")
    nomi = {"massaggio_cardiaco": "Massaggio Cardiaco (BLS-D)", "heimlich": "Manovra di Heimlich"}
    await db["corsi"].insert_one({
        "tipo": tipo,
        "nome": nomi.get(tipo, tipo),
        "data": form.get("data"),
        "ora": form.get("ora"),
        "luogo": form.get("luogo"),
        "max_partecipanti": int(form.get("max_partecipanti", 20)),
        "note": form.get("note", ""),
        "attivo": False,
        "creato_da": user["username"],
        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
    return JSONResponse({"status": "ok"})


@router.post("/corsi/toggle")
async def corso_toggle(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    attivo = form.get("attivo") == "true"
    await db["corsi"].update_one(
        {"_id": ObjectId(form.get("corso_id"))},
        {"$set": {"attivo": attivo}}
    )
    return JSONResponse({"status": "ok"})


@router.post("/corsi/elimina")
async def corso_elimina(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    await db["corsi"].delete_one({"_id": ObjectId(form.get("corso_id"))})
    return JSONResponse({"status": "ok"})


@router.post("/corsi/valuta")
async def corso_valuta(request: Request, user: dict = Depends(require_permission(10)), db=Depends(get_db)):
    from bson import ObjectId
    from datetime import datetime
    form = await request.form()
    await db["prenotazioni_corsi"].update_one(
        {"_id": ObjectId(form.get("iscrizione_id"))},
        {"$set": {
            "esito": form.get("esito"),
            "valutato_da": user["username"],
            "valutato_il": datetime.now().strftime("%d/%m/%Y %H:%M"),
        }}
    )
    return JSONResponse({"status": "ok"})


# ─── SCHEDA PAZIENTE ─────────────────────────────────────────────────────────

@router.get("/pazienti/scheda/{paziente_id}", response_class=HTMLResponse)
async def scheda_paziente(paziente_id: str, request: Request, user: dict = Depends(require_permission(10)), db=Depends(get_db)):
    from bson import ObjectId
    from datetime import datetime, date
    paziente = await db["pazienti"].find_one({"_id": ObjectId(paziente_id)})
    if not paziente:
        return HTMLResponse("Paziente non trovato", status_code=404)

    # Calcola età
    eta = "—"
    try:
        dn = paziente.get("data_nascita", "")
        if dn:
            nascita = datetime.strptime(dn, "%Y-%m-%d")
            oggi = datetime.now()
            eta = oggi.year - nascita.year - ((oggi.month, oggi.day) < (nascita.month, nascita.day))
    except Exception:
        pass

    referti = await db["documenti"].find({"paziente_id": str(paziente["_id"])}).sort("timestamp", -1).to_list(100)
    visite = await db["prenotazioni_visite"].find({"discord_id": paziente.get("discord_id", "")}).sort("timestamp", -1).to_list(50)
    corsi = await db["prenotazioni_corsi"].find({"discord_id": paziente.get("discord_id", "")}).sort("timestamp", -1).to_list(50)

    return templates.TemplateResponse("scheda_paziente.html", {
        "request": request,
        "user": user,
        "paziente": paziente,
        "eta": eta,
        "referti": referti,
        "visite": visite,
        "corsi": corsi,
    })


@router.get("/pazienti/cerca", response_class=HTMLResponse)
async def cerca_paziente(request: Request, tessera: str = "", user: dict = Depends(require_permission(10)), db=Depends(get_db)):
    paziente = None
    if tessera:
        paziente = await db["pazienti"].find_one({"numero_tessera": tessera.strip().upper()})
    return templates.TemplateResponse("cerca_paziente.html", {
        "request": request,
        "user": user,
        "paziente": paziente,
        "tessera": tessera,
        "non_trovato": tessera and not paziente,
    })


@router.post("/pazienti/referto/aggiungi")
async def aggiungi_referto(request: Request, user: dict = Depends(require_permission(10)), db=Depends(get_db)):
    from bson import ObjectId
    from datetime import datetime
    form = await request.form()
    await db["documenti"].insert_one({
        "paziente_id": form.get("paziente_id"),
        "titolo": form.get("titolo"),
        "categoria": form.get("categoria"),
        "contenuto": form.get("contenuto"),
        "medico": user["username"],
        "medico_id": user["discord_id"],
        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "visibile_paziente": True,
    })
    return JSONResponse({"status": "ok"})


@router.get("/cittadini", response_class=HTMLResponse)
async def gestione_cittadini(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    cittadini = await db["cittadini"].find().sort("registrato_il", -1).to_list(200)
    return templates.TemplateResponse("gestione_cittadini.html", {
        "request": request,
        "user": user,
        "cittadini": cittadini,
    })


@router.post("/cittadini/elimina")
async def elimina_cittadino(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    form = await request.form()
    await db["cittadini"].delete_one({"discord_id": form.get("discord_id")})
    return JSONResponse({"status": "ok"})


@router.post("/pec/elimina")
async def elimina_pec(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    await db["pec"].delete_one({"_id": ObjectId(form.get("pec_id"))})
    return JSONResponse({"status": "ok"})


# ─── VISITE ──────────────────────────────────────────────────────────────────

@router.post("/visite/aggiorna")
async def visita_aggiorna(request: Request, user: dict = Depends(require_permission(10)), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    visita_id = form.get("visita_id")
    azione = form.get("azione")  # accetta, rifiuta, completa, modifica_ora
    update = {}
    if azione == "accetta":
        update = {"stato": "in_carico", "medico_assegnato": user["username"], "medico_id": user["discord_id"]}
    elif azione == "rifiuta":
        update = {"stato": "rifiutata", "motivo_rifiuto": form.get("motivo", "")}
    elif azione == "completa":
        update = {"stato": "completata"}
    elif azione == "modifica_ora":
        update = {"ora_confermata": form.get("ora"), "data_confermata": form.get("data")}
    if update:
        await db["prenotazioni_visite"].update_one({"_id": ObjectId(visita_id)}, {"$set": update})
    # Notifica DM al paziente
    try:
        from bot.cogs import get_bot
        visita = await db["prenotazioni_visite"].find_one({"_id": ObjectId(visita_id)})
        if visita and visita.get("discord_id"):
            bot = get_bot()
            if bot:
                dest = await bot.fetch_user(int(visita["discord_id"]))
                msgs = {
                    "accetta": f"✅ La tua visita **{visita.get('tipo_visita')}** è stata accettata dal Dr. {user['username']}.",
                    "rifiuta": f"❌ La tua visita **{visita.get('tipo_visita')}** è stata rifiutata. Motivo: {form.get('motivo', '—')}",
                    "completa": f"✅ La tua visita **{visita.get('tipo_visita')}** è stata completata.",
                    "modifica_ora": f"📅 L'orario della tua visita **{visita.get('tipo_visita')}** è stato aggiornato: {form.get('data')} alle {form.get('ora')}.",
                }
                if dest and azione in msgs:
                    await dest.send(msgs[azione])
    except Exception as e:
        print(f"[VISITA] Errore DM: {e}")
    return JSONResponse({"status": "ok"})


@router.post("/visite/aggiungi")
async def visita_aggiungi(request: Request, user: dict = Depends(require_permission(10)), db=Depends(get_db)):
    from datetime import datetime
    form = await request.form()
    await db["prenotazioni_visite"].insert_one({
        "discord_id": form.get("discord_id", ""),
        "nome_paziente": form.get("nome_paziente"),
        "numero_tessera": form.get("numero_tessera", ""),
        "tipo_visita": form.get("tipo_visita"),
        "data_richiesta": form.get("data_richiesta"),
        "ora_preferita": form.get("ora_preferita", ""),
        "note": form.get("note", ""),
        "stato": "in_carico",
        "medico_assegnato": user["username"],
        "medico_id": user["discord_id"],
        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
    return JSONResponse({"status": "ok"})


@router.post("/visite/referto")
async def visita_referto(request: Request, user: dict = Depends(require_permission(10)), db=Depends(get_db)):
    from bson import ObjectId
    from datetime import datetime
    form = await request.form()
    visita_id = form.get("visita_id")
    paziente_id = form.get("paziente_id")
    await db["prenotazioni_visite"].update_one(
        {"_id": ObjectId(visita_id)},
        {"$set": {"stato": "completata", "referto_id": visita_id}}
    )
    await db["documenti"].insert_one({
        "paziente_id": paziente_id,
        "titolo": f"Referto visita — {form.get('tipo_visita', '')}",
        "categoria": "referto",
        "contenuto": form.get("contenuto"),
        "medico": user["username"],
        "medico_id": user["discord_id"],
        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "visibile_paziente": True,
    })
    return JSONResponse({"status": "ok"})


@router.post("/pazienti/archivia")
async def archivia_paziente(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    paziente_id = form.get("paziente_id")
    await db["pazienti"].update_one(
        {"_id": ObjectId(paziente_id)},
        {"$set": {"archiviato": True, "stato": "Deceduto", "discord_id": None}}
    )
    return JSONResponse({"status": "ok"})
