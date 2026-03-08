import httpx
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from jose import jwt, JWTError
from datetime import datetime, timedelta
from bson import ObjectId
import os

router = APIRouter(prefix="/cittadini", tags=["cittadini"])
templates = Jinja2Templates(directory="templates/cittadini")

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 8
COOKIE_NAME = "cittadino_token"

TIPI_VISITA = {
    "Medicina Generale":     None,
    "Pronto Soccorso":       "ROLE_PRIMARIO",
    "Cardiologia":           "ROLE_SPECIALISTA",
    "Chirurgia":             "ROLE_SPECIALISTA",
    "Laboratorio Analisi":   "ROLE_MED_FORMAZIONE",
    "Farmacia":              "ROLE_RESP_FARMACIA",
    "Pediatria":             "ROLE_SPECIALISTA",
    "Neurologia":            "ROLE_SPECIALISTA",
    "Ortopedia":             "ROLE_SPECIALISTA",
    "Psicologia":            "ROLE_MED_FORMAZIONE",
}

CORSI_DISPONIBILI = [
    {
        "id": "massaggio_cardiaco",
        "nome": "Massaggio Cardiaco (BLS-D)",
        "descrizione": "Corso base di rianimazione cardiopolmonare e uso del defibrillatore.",
        "durata": "4 ore",
        "posti": 20,
    },
    {
        "id": "heimlich",
        "nome": "Manovra di Heimlich",
        "descrizione": "Tecnica di disostruzione delle vie aeree per adulti e bambini.",
        "durata": "2 ore",
        "posti": 20,
    },
]


def get_secret():
    return os.getenv("SECRET_KEY", "dev-secret-change-me")


def create_cittadino_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS)
    return jwt.encode(payload, get_secret(), algorithm=JWT_ALGORITHM)


def decode_cittadino_token(token: str) -> dict:
    return jwt.decode(token, get_secret(), algorithms=[JWT_ALGORITHM])


async def get_cittadino(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        return decode_cittadino_token(token)
    except JWTError:
        return None


async def require_cittadino(request: Request):
    user = await get_cittadino(request)
    if not user:
        return RedirectResponse("/cittadini/login")
    return user


# ─── HOME ───────────────────────────────────────────────────────────────────

@router.get("/")
async def cittadini_home(request: Request):
    user = await get_cittadino(request)
    if user:
        return RedirectResponse("/cittadini/dashboard")
    return templates.TemplateResponse("home.html", {"request": request})


# ─── AUTH ────────────────────────────────────────────────────────────────────

@router.get("/login")
async def cittadini_login():
    from config import DISCORD_CLIENT_ID, DISCORD_REDIRECT_URI
    # Redirect OAuth con scope diverso (solo identify, no guild)
    callback_uri = DISCORD_REDIRECT_URI.replace("/auth/callback", "/cittadini/auth/callback")
    url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={callback_uri}"
        f"&response_type=code"
        f"&scope=identify"
    )
    return RedirectResponse(url)


@router.get("/auth/callback")
async def cittadini_callback(request: Request, code: str):
    from config import (
        DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET,
        DISCORD_API_BASE, DISCORD_REDIRECT_URI,
    )
    from database import get_db
    db = get_db()

    callback_uri = DISCORD_REDIRECT_URI.replace("/auth/callback", "/cittadini/auth/callback")

    async with httpx.AsyncClient() as client:
        token_res = await client.post(
            f"{DISCORD_API_BASE}/oauth2/token",
            data={
                "client_id":     DISCORD_CLIENT_ID,
                "client_secret": DISCORD_CLIENT_SECRET,
                "grant_type":    "authorization_code",
                "code":          code,
                "redirect_uri":  callback_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_res.status_code != 200:
            return templates.TemplateResponse("errore.html", {
                "request": request,
                "motivo": "Errore durante l'autenticazione Discord."
            })
        access_token = token_res.json()["access_token"]

        user_res = await client.get(
            f"{DISCORD_API_BASE}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if user_res.status_code != 200:
            return templates.TemplateResponse("errore.html", {
                "request": request,
                "motivo": "Impossibile ottenere il profilo Discord."
            })
        user = user_res.json()

    discord_id = user["id"]
    username = user.get("username", "")
    avatar = user.get("avatar")

    # Salva se è un dipendente per mostrare funzioni extra
    dipendente = await db["dipendenti"].find_one({"discord_id": discord_id})
    is_medico = dipendente is not None

    # Registra o aggiorna cittadino
    existing = await db["cittadini"].find_one({"discord_id": discord_id})
    if not existing:
        await db["cittadini"].insert_one({
            "discord_id": discord_id,
            "username": username,
            "avatar": avatar,
            "tessera": None,
            "registrato_il": datetime.now().strftime("%d/%m/%Y %H:%M"),
        })

    token = create_cittadino_token({
        "discord_id": discord_id,
        "username": username,
        "avatar": avatar,
    })
    redirect = RedirectResponse("/cittadini/dashboard")
    redirect.set_cookie(
        key=COOKIE_NAME, value=token,
        httponly=True, samesite="lax",
        max_age=JWT_EXPIRE_HOURS * 3600,
    )
    return redirect


@router.get("/logout")
async def cittadini_logout():
    resp = RedirectResponse("/cittadini/")
    resp.delete_cookie(COOKIE_NAME)
    return resp


# ─── DASHBOARD ───────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def cittadini_dashboard(request: Request):
    user = await get_cittadino(request)
    if not user:
        return RedirectResponse("/cittadini/login")
    from database import get_db
    db = get_db()
    discord_id = user["discord_id"]
    cittadino = await db["cittadini"].find_one({"discord_id": discord_id})
    tessera = cittadino.get("tessera") if cittadino else None

    # Conta prenotazioni attive
    n_visite = await db["prenotazioni_visite"].count_documents({
        "discord_id": discord_id, "stato": {"$ne": "completata"}
    })
    n_corsi = await db["prenotazioni_corsi"].count_documents({
        "discord_id": discord_id, "stato": {"$ne": "completata"}
    })
    # Referti del paziente
    n_referti = 0
    if tessera:
        paziente = await db["pazienti"].find_one({"discord_id": discord_id})
        if paziente:
            n_referti = await db["documenti"].count_documents({
                "paziente_id": str(paziente["_id"]),
                "categoria": {"$in": ["referto", "cartella_clinica"]},
            })

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "tessera": tessera,
        "n_visite": n_visite,
        "n_corsi": n_corsi,
        "n_referti": n_referti,
    })


# ─── TESSERA SANITARIA ────────────────────────────────────────────────────────

@router.get("/tessera")
async def tessera_page(request: Request):
    user = await get_cittadino(request)
    if not user:
        return RedirectResponse("/cittadini/login")
    from database import get_db
    db = get_db()
    cittadino = await db["cittadini"].find_one({"discord_id": user["discord_id"]})
    tessera = cittadino.get("tessera") if cittadino else None
    return templates.TemplateResponse("tessera.html", {
        "request": request,
        "user": user,
        "tessera": tessera,
    })


@router.post("/tessera/crea")
async def tessera_crea(request: Request):
    user = await get_cittadino(request)
    if not user:
        return JSONResponse({"status": "error", "detail": "Non autenticato."})
    from database import get_db
    db = get_db()
    discord_id = user["discord_id"]
    form = await request.form()

    cittadino = await db["cittadini"].find_one({"discord_id": discord_id})
    if cittadino and cittadino.get("tessera"):
        return JSONResponse({"status": "error", "detail": "Tessera già esistente."})

    # Genera numero tessera
    count = await db["cittadini"].count_documents({"tessera": {"$ne": None}})
    numero_tessera = f"OSC-{datetime.now().year}-{str(count + 1).zfill(5)}"

    tessera = {
        "numero": numero_tessera,
        "nome": form.get("nome", "").strip(),
        "cognome": form.get("cognome", "").strip(),
        "data_nascita": form.get("data_nascita", "").strip(),
        "codice_fiscale": form.get("codice_fiscale", "").strip().upper(),
        "indirizzo": form.get("indirizzo", "").strip(),
        "gruppo_sanguigno": form.get("gruppo_sanguigno", "").strip(),
        "allergie": form.get("allergie", "").strip(),
        "creata_il": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }

    await db["cittadini"].update_one(
        {"discord_id": discord_id},
        {"$set": {"tessera": tessera}}
    )

    # Crea anche il paziente nel gestionale
    existing_paz = await db["pazienti"].find_one({"discord_id": discord_id})
    if not existing_paz:
        await db["pazienti"].insert_one({
            "discord_id": discord_id,
            "nome": tessera["nome"],
            "cognome": tessera["cognome"],
            "data_nascita": tessera["data_nascita"],
            "codice_fiscale": tessera["codice_fiscale"],
            "indirizzo": tessera["indirizzo"],
            "gruppo_sanguigno": tessera["gruppo_sanguigno"],
            "allergie": tessera["allergie"],
            "numero_tessera": numero_tessera,
            "stato": "attivo",
            "added_by": "Portale Cittadini",
            "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
        })

    return JSONResponse({"status": "ok", "numero": numero_tessera})


# ─── PRENOTAZIONI VISITE ──────────────────────────────────────────────────────

@router.get("/prenotazioni")
async def prenotazioni_page(request: Request):
    user = await get_cittadino(request)
    if not user:
        return RedirectResponse("/cittadini/login")
    from database import get_db
    db = get_db()
    discord_id = user["discord_id"]
    cittadino = await db["cittadini"].find_one({"discord_id": discord_id})
    if not cittadino or not cittadino.get("tessera"):
        return RedirectResponse("/cittadini/tessera")

    prenotazioni = await db["prenotazioni_visite"].find(
        {"discord_id": discord_id}
    ).sort("timestamp", -1).to_list(50)

    return templates.TemplateResponse("prenotazioni.html", {
        "request": request,
        "user": user,
        "tessera": cittadino["tessera"],
        "prenotazioni": prenotazioni,
        "tipi_visita": list(TIPI_VISITA.keys()),
    })


@router.post("/prenotazioni/nuova")
async def prenotazione_nuova(request: Request):
    user = await get_cittadino(request)
    if not user:
        return JSONResponse({"status": "error", "detail": "Non autenticato."})
    from database import get_db
    db = get_db()
    discord_id = user["discord_id"]
    form = await request.form()

    cittadino = await db["cittadini"].find_one({"discord_id": discord_id})
    if not cittadino or not cittadino.get("tessera"):
        return JSONResponse({"status": "error", "detail": "Tessera sanitaria richiesta."})

    tipo_visita = form.get("tipo_visita", "")
    await db["prenotazioni_visite"].insert_one({
        "discord_id": discord_id,
        "nome_paziente": f"{cittadino['tessera']['nome']} {cittadino['tessera']['cognome']}",
        "numero_tessera": cittadino["tessera"]["numero"],
        "tipo_visita": tipo_visita,
        "data_richiesta": form.get("data_richiesta", ""),
        "ora_preferita": form.get("ora_preferita", ""),
        "note": form.get("note", "").strip(),
        "stato": "in_attesa",
        "medico_assegnato": None,
        "ruolo_richiesto": TIPI_VISITA.get(tipo_visita),
        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
    return JSONResponse({"status": "ok", "message": "Prenotazione inviata con successo."})


@router.post("/prenotazioni/annulla")
async def prenotazione_annulla(request: Request):
    user = await get_cittadino(request)
    if not user:
        return JSONResponse({"status": "error", "detail": "Non autenticato."})
    from database import get_db
    db = get_db()
    form = await request.form()
    prenotazione_id = form.get("prenotazione_id")
    await db["prenotazioni_visite"].update_one(
        {"_id": ObjectId(prenotazione_id), "discord_id": user["discord_id"]},
        {"$set": {"stato": "annullata"}}
    )
    return JSONResponse({"status": "ok"})


# ─── REFERTI ─────────────────────────────────────────────────────────────────

@router.get("/referti")
async def referti_page(request: Request):
    user = await get_cittadino(request)
    if not user:
        return RedirectResponse("/cittadini/login")
    from database import get_db
    db = get_db()
    discord_id = user["discord_id"]

    cittadino = await db["cittadini"].find_one({"discord_id": discord_id})
    if not cittadino or not cittadino.get("tessera"):
        return RedirectResponse("/cittadini/tessera")

    paziente = await db["pazienti"].find_one({"discord_id": discord_id})
    documenti = []
    if paziente:
        documenti = await db["documenti"].find({
            "paziente_id": str(paziente["_id"]),
            "categoria": {"$in": ["referto", "cartella_clinica"]},
        }).sort("timestamp", -1).to_list(100)

    return templates.TemplateResponse("referti.html", {
        "request": request,
        "user": user,
        "tessera": cittadino["tessera"],
        "documenti": documenti,
    })


# ─── CANDIDATURA MEDICO ───────────────────────────────────────────────────────

@router.get("/candidatura")
async def candidatura_page(request: Request):
    user = await get_cittadino(request)
    if not user:
        return RedirectResponse("/cittadini/login")
    from database import get_db
    db = get_db()
    discord_id = user["discord_id"]

    # Controlla se ha già candidatura attiva
    candidatura = await db["candidature_medico"].find_one({
        "discord_id": discord_id,
        "stato": {"$in": ["in_attesa", "in_revisione"]},
    })

    return templates.TemplateResponse("candidatura.html", {
        "request": request,
        "user": user,
        "candidatura_attiva": candidatura,
    })


@router.post("/candidatura/invia")
async def candidatura_invia(request: Request):
    user = await get_cittadino(request)
    if not user:
        return JSONResponse({"status": "error", "detail": "Non autenticato."})
    from database import get_db
    db = get_db()
    discord_id = user["discord_id"]
    form = await request.form()

    # Controlla candidatura duplicata
    existing = await db["candidature_medico"].find_one({
        "discord_id": discord_id,
        "stato": {"$in": ["in_attesa", "in_revisione"]},
    })
    if existing:
        return JSONResponse({"status": "error", "detail": "Hai già una candidatura in corso."})

    # Controlla che non sia già dipendente
    dip = await db["dipendenti"].find_one({"discord_id": discord_id})
    if dip:
        return JSONResponse({"status": "error", "detail": "Sei già registrato come personale."})

    await db["candidature_medico"].insert_one({
        "discord_id": discord_id,
        "username": user["username"],
        "nome": form.get("nome", "").strip(),
        "cognome": form.get("cognome", "").strip(),
        "eta": form.get("eta", "").strip(),
        "titolo_studio": form.get("titolo_studio", "").strip(),
        "specializzazione": form.get("specializzazione", "").strip(),
        "esperienza": form.get("esperienza", "").strip(),
        "motivazione": form.get("motivazione", "").strip(),
        "ruolo_desiderato": form.get("ruolo_desiderato", "").strip(),
        "stato": "in_attesa",
        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "approvata_da": None,
        "approvata_il": None,
    })

    # Notifica al Direttore via bot
    try:
        await _notifica_candidatura(discord_id, user["username"], form.get("nome", ""), form.get("cognome", ""))
    except Exception:
        pass

    return JSONResponse({"status": "ok", "message": "Candidatura inviata! Sarai contattato presto."})


async def _notifica_candidatura(discord_id: str, username: str, nome: str, cognome: str):
    from bot.cogs import get_bot
    import nextcord
    from config import ROLE_DIRETTORE_ID, DISCORD_GUILD_ID
    bot = get_bot()
    if not bot:
        return
    guild = bot.get_guild(int(DISCORD_GUILD_ID))
    if not guild:
        return
    role = guild.get_role(int(ROLE_DIRETTORE_ID))
    if not role:
        return
    embed = nextcord.Embed(
        title="🏥 Nuova Candidatura Medico",
        color=0x2563eb,
        timestamp=datetime.utcnow(),
    )
    embed.add_field(name="👤 Utente", value=f"{nome} {cognome} (<@{discord_id}>)", inline=False)
    embed.add_field(name="📋 Username Discord", value=username, inline=True)
    embed.add_field(name="✅ Azione", value="Vai su Gestionale → Candidature per approvare.", inline=False)
    embed.set_footer(text="Ospedale San Camillo — Portale Cittadini")
    for member in role.members:
        try:
            await member.send(embed=embed)
        except Exception:
            pass


# ─── CORSI PRIMO SOCCORSO ─────────────────────────────────────────────────────

@router.get("/corsi")
async def corsi_page(request: Request):
    user = await get_cittadino(request)
    if not user:
        return RedirectResponse("/cittadini/login")
    from database import get_db
    db = get_db()
    discord_id = user["discord_id"]

    mie_prenotazioni = await db["prenotazioni_corsi"].find(
        {"discord_id": discord_id}
    ).sort("timestamp", -1).to_list(20)
    prenotati = {p["corso_id"] for p in mie_prenotazioni if p.get("stato") != "annullata"}

    # Conta posti disponibili per ogni corso
    corsi_db = await db["corsi"].find({"attivo": True}).to_list(50)
    corsi_con_posti = []
    for corso in corsi_db:
        corso_id = str(corso["_id"])
        prenotati_count = await db["prenotazioni_corsi"].count_documents({
            "corso_id": corso_id,
            "stato": {"$ne": "annullata"},
        })
        corsi_con_posti.append({
            "id": corso_id,
            "nome": corso["nome"],
            "descrizione": corso.get("note", ""),
            "durata": "Vedi dettagli",
            "data": corso.get("data", ""),
            "ora": corso.get("ora", ""),
            "luogo": corso.get("luogo", ""),
            "posti": corso["max_partecipanti"],
            "posti_disponibili": max(0, corso["max_partecipanti"] - prenotati_count),
            "prenotato": corso_id in prenotati,
        })

    return templates.TemplateResponse("corsi.html", {
        "request": request,
        "user": user,
        "corsi": corsi_con_posti,
        "mie_prenotazioni": mie_prenotazioni,
    })


@router.post("/corsi/prenota")
async def corso_prenota(request: Request):
    user = await get_cittadino(request)
    if not user:
        return JSONResponse({"status": "error", "detail": "Non autenticato."})
    from database import get_db
    db = get_db()
    discord_id = user["discord_id"]
    form = await request.form()
    corso_id = form.get("corso_id")

    corso = next((c for c in CORSI_DISPONIBILI if c["id"] == corso_id), None)
    if not corso:
        return JSONResponse({"status": "error", "detail": "Corso non trovato."})

    # Controlla posti
    prenotati_count = await db["prenotazioni_corsi"].count_documents({
        "corso_id": corso_id, "stato": {"$ne": "annullata"}
    })
    if prenotati_count >= corso["posti"]:
        return JSONResponse({"status": "error", "detail": "Nessun posto disponibile."})

    # Controlla duplicato
    existing = await db["prenotazioni_corsi"].find_one({
        "discord_id": discord_id,
        "corso_id": corso_id,
        "stato": {"$ne": "annullata"},
    })
    if existing:
        return JSONResponse({"status": "error", "detail": "Sei già iscritto a questo corso."})

    await db["prenotazioni_corsi"].insert_one({
        "discord_id": discord_id,
        "username": user["username"],
        "corso_id": corso_id,
        "corso_nome": corso["nome"],
        "data_preferita": form.get("data_preferita", ""),
        "stato": "confermata",
        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
    return JSONResponse({"status": "ok", "message": f"Iscritto a: {corso['nome']}"})


# ─── MESSAGGI ────────────────────────────────────────────────────────────────

@router.get("/messaggi", response_class=HTMLResponse)
async def messaggi_page(request: Request):
    from database import get_db as _get_db
    from datetime import datetime
    cittadino = await require_cittadino(request)
    if isinstance(cittadino, RedirectResponse): return cittadino
    db = await _get_db().__anext__()
    messaggi_ricevuti = await db["pec"].find({
        "destinatario": f"cittadino:{cittadino['discord_id']}"
    }).sort("timestamp", -1).to_list(50)
    messaggi_inviati = await db["pec"].find({
        "mittente_id": cittadino["discord_id"],
        "mittente_tipo": "cittadino"
    }).sort("timestamp", -1).to_list(50)
    dipendenti = await db["dipendenti"].find({"approvato": True}).to_list(100)
    return templates.TemplateResponse("cittadini/messaggi.html", {
        "request": request,
        "cittadino": cittadino,
        "ricevuti": messaggi_ricevuti,
        "inviati": messaggi_inviati,
        "dipendenti": dipendenti,
        "reparti": [
            {"id": "reparto:pronto_soccorso", "nome": "🚨 Pronto Soccorso"},
            {"id": "reparto:degenze", "nome": "🛏️ Reparto Degenze"},
            {"id": "reparto:chirurgia", "nome": "✂️ Chirurgia"},
            {"id": "reparto:laboratorio", "nome": "🔬 Laboratorio Analisi"},
            {"id": "reparto:farmacia", "nome": "💊 Farmacia"},
            {"id": "reparto:amministrazione", "nome": "📁 Amministrazione"},
        ],
    })


@router.post("/messaggi/invia")
async def messaggi_invia(request: Request):
    from database import get_db as _get_db
    from datetime import datetime
    cittadino = await require_cittadino(request)
    if isinstance(cittadino, RedirectResponse): return cittadino
    db = await _get_db().__anext__()
    form = await request.form()
    await db["pec"].insert_one({
        "destinatario": form.get("destinatario"),
        "oggetto": form.get("oggetto"),
        "corpo": form.get("corpo"),
        "priorita": "normale",
        "mittente": cittadino["username"],
        "mittente_id": cittadino["discord_id"],
        "mittente_tipo": "cittadino",
        "stato": "inviata",
        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
    return JSONResponse({"status": "ok"})
