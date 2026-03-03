from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
from auth import get_current_user, require_permission
from database import get_db
from config import TUTTI_RUOLI, RUOLI_DIRIGENZA, RUOLI_REPARTO, RUOLI_TIROCINIO

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
templates = Jinja2Templates(directory="templates")


# ── DASHBOARD ─────────────────────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    stats = {
        "dipendenti_totali": await db["dipendenti"].count_documents({}),
        "pazienti_attivi":   await db["pazienti"].count_documents({"status": "ricoverato"}),
        "documenti":         await db["documenti"].count_documents({}),
        "richiami_attivi":   await db["richiami"].count_documents({"status": "attivo"}),
        "segnalazioni":      await db["segnalazioni"].count_documents({"status": "aperta"}),
        "comunicati":        await db["comunicati"].count_documents({}),
    }
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user,
        "stats": stats, "active_section": "dashboard",
    })


# ── DIPENDENTI ────────────────────────────────────────────────────────────────
@router.get("/dipendenti/dirigenza", response_class=HTMLResponse)
async def dipendenti_dirigenza(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    lista = await db["dipendenti"].find({"categoria": "dirigenza"}).to_list(100)
    return templates.TemplateResponse("dipendenti.html", {
        "request": request, "user": user,
        "dipendenti": lista, "categoria": "Dirigenza",
        "ruoli": RUOLI_DIRIGENZA, "active_section": "dirigenza",
    })

@router.get("/dipendenti/reparto", response_class=HTMLResponse)
async def dipendenti_reparto(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    lista = await db["dipendenti"].find({"categoria": "reparto"}).to_list(100)
    return templates.TemplateResponse("dipendenti.html", {
        "request": request, "user": user,
        "dipendenti": lista, "categoria": "Reparto",
        "ruoli": RUOLI_REPARTO, "active_section": "reparto",
    })

@router.get("/dipendenti/tirocinio", response_class=HTMLResponse)
async def dipendenti_tirocinio(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    lista = await db["dipendenti"].find({"categoria": "tirocinio"}).to_list(100)
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
    lista = await db["pazienti"].find().sort("timestamp", -1).to_list(100)
    dipendenti = await db["dipendenti"].find().to_list(100)
    return templates.TemplateResponse("pazienti.html", {
        "request": request, "user": user,
        "pazienti": lista, "dipendenti": dipendenti,
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
    query = {} if categoria == "tutti" else {"categoria": categoria}
    docs = await db["documenti"].find(query).sort("timestamp", -1).to_list(100)
    return templates.TemplateResponse("documenti.html", {
        "request": request, "user": user,
        "docs": docs, "categoria_attiva": categoria,
        "active_section": "documenti",
    })

@router.post("/documenti/add")
async def add_documento(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    form = await request.form()
    await db["documenti"].insert_one({
        "titolo":      form.get("titolo"),
        "categoria":   form.get("categoria"),
        "contenuto":   form.get("contenuto"),
        "riferimento": form.get("riferimento", ""),
        "author":      user["username"],
        "timestamp":   datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
    return {"status": "ok", "message": "Documento aggiunto."}


# ── RICHIAMI ──────────────────────────────────────────────────────────────────
@router.get("/richiami", response_class=HTMLResponse)
async def richiami(request: Request, user: dict = Depends(require_permission(50)), db=Depends(get_db)):
    lista = await db["richiami"].find().sort("timestamp", -1).to_list(100)
    dipendenti = await db["dipendenti"].find().to_list(100)
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
        "titolo":    form.get("titolo"),
        "contenuto": form.get("contenuto"),
        "priority":  form.get("priority"),
        "author":    user["username"],
        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
    return {"status": "ok", "message": "Comunicato pubblicato."}


# ── PEC ───────────────────────────────────────────────────────────────────────
@router.get("/pec", response_class=HTMLResponse)
async def pec(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    pec_list = await db["pec"].find().sort("timestamp", -1).to_list(50)
    dipendenti = await db["dipendenti"].find().to_list(100)
    return templates.TemplateResponse("pec.html", {
        "request": request, "user": user,
        "pec_list": pec_list, "dipendenti": dipendenti,
        "active_section": "pec",
    })

@router.post("/pec/send")
async def send_pec(request: Request, user: dict = Depends(get_current_user), db=Depends(get_db)):
    form = await request.form()
    await db["pec"].insert_one({
        "destinatario": form.get("destinatario"),
        "oggetto":      form.get("oggetto"),
        "corpo":        form.get("corpo"),
        "mittente":     user["username"],
        "stato":        "inviata",
        "timestamp":    datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
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
        "dipendenti_totali":  await db["dipendenti"].count_documents({}),
        "dirigenza":          await db["dipendenti"].count_documents({"categoria": "dirigenza"}),
        "reparto":            await db["dipendenti"].count_documents({"categoria": "reparto"}),
        "tirocinio":          await db["dipendenti"].count_documents({"categoria": "tirocinio"}),
        "pazienti_totali":    await db["pazienti"].count_documents({}),
        "pazienti_ricoverati":await db["pazienti"].count_documents({"status": "ricoverato"}),
        "pazienti_dimessi":   await db["pazienti"].count_documents({"status": "dimesso"}),
        "richiami_attivi":    await db["richiami"].count_documents({"status": "attivo"}),
        "richiami_chiusi":    await db["richiami"].count_documents({"status": "chiuso"}),
        "segnalazioni_aperte":await db["segnalazioni"].count_documents({"status": "aperta"}),
        "documenti_totali":   await db["documenti"].count_documents({}),
    }
    return templates.TemplateResponse("statistiche.html", {
        "request": request, "user": user,
        "stats": stats, "active_section": "statistiche",
    })


# ── GESTIONE UTENTI ───────────────────────────────────────────────────────────
@router.get("/utenti", response_class=HTMLResponse)
async def utenti(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    lista = await db["dipendenti"].find().to_list(100)
    return templates.TemplateResponse("utenti.html", {
        "request": request, "user": user,
        "dipendenti": lista, "active_section": "utenti",
        "tutti_ruoli": TUTTI_RUOLI,
    })

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


@router.post("/segnalazioni/aggiorna")
async def aggiorna_segnalazione(request: Request, user: dict = Depends(require_permission(50)), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    await db["segnalazioni"].update_one(
        {"_id": ObjectId(form.get("segnalazione_id"))},
        {"$set": {"status": form.get("status")}}
    )
    return {"status": "ok", "message": "Segnalazione aggiornata."}


@router.post("/richiami/elimina")
async def elimina_richiamo(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    await db["richiami"].delete_one({"_id": ObjectId(form.get("richiamo_id"))})
    return {"status": "ok", "message": "Richiamo eliminato."}


@router.post("/richiami/elimina")
async def elimina_richiamo(request: Request, user: dict = Depends(require_permission(100)), db=Depends(get_db)):
    from bson import ObjectId
    form = await request.form()
    await db["richiami"].delete_one({"_id": ObjectId(form.get("richiamo_id"))})
    return {"status": "ok", "message": "Richiamo eliminato."}
