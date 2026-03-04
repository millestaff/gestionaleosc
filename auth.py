import httpx
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from jose import jwt, JWTError
from datetime import datetime, timedelta
from config import (
    DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET,
    DISCORD_REDIRECT_URI, DISCORD_API_BASE,
    DISCORD_GUILD_ID, SECRET_KEY, ROLE_PERMISSIONS,
    RUOLI_DIRIGENZA, RUOLI_REPARTO, RUOLI_TIROCINIO,
)

router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="templates")

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 8
COOKIE_NAME = "session_token"


def create_session_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS)
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_session_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])


def calculate_permission(role_ids: list[str]) -> int:
    level = 0
    for role_id in role_ids:
        level = max(level, ROLE_PERMISSIONS.get(role_id, 0))
    return level


def get_role_name(role_ids: list[str]) -> str:
    for role_id in role_ids:
        if role_id in ROLE_PERMISSIONS:
            level = ROLE_PERMISSIONS[role_id]
            if level == 100:
                return "Direttore"
            elif level == 50:
                return "Dirigenza"
            else:
                return "Personale"
    return "Sconosciuto"


@router.get("/login")
async def login():
    url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={DISCORD_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify+guilds.members.read"
    )
    return RedirectResponse(url)


@router.get("/callback")
async def callback(request: Request, code: str):
    from database import get_db
    db = get_db()

    async with httpx.AsyncClient() as client:
        token_res = await client.post(
            f"{DISCORD_API_BASE}/oauth2/token",
            data={
                "client_id":     DISCORD_CLIENT_ID,
                "client_secret": DISCORD_CLIENT_SECRET,
                "grant_type":    "authorization_code",
                "code":          code,
                "redirect_uri":  DISCORD_REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_res.status_code != 200:
            raise HTTPException(400, "Errore token Discord.")
        access_token = token_res.json()["access_token"]

        user_res = await client.get(
            f"{DISCORD_API_BASE}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if user_res.status_code != 200:
            raise HTTPException(400, "Impossibile ottenere profilo Discord.")
        user = user_res.json()

        member_res = await client.get(
            f"{DISCORD_API_BASE}/users/@me/guilds/{DISCORD_GUILD_ID}/member",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        role_ids: list[str] = []
        nick = user.get("username")
        if member_res.status_code == 200:
            member_data = member_res.json()
            role_ids = member_data.get("roles", [])
            nick = member_data.get("nick") or nick

    # Calcola permesso
    permission = calculate_permission(role_ids)

    # Nessun ruolo riconosciuto
    if permission == 0:
        return templates.TemplateResponse("accesso_negato.html", {
            "request":  request,
            "username": user.get("username", ""),
            "motivo":   "Il tuo account Discord non ha nessun ruolo autorizzato. Contatta il Direttore."
        }, status_code=403)

    discord_id = user["id"]

    # Controlla se esiste già nel DB
    existing = await db["dipendenti"].find_one({"discord_id": discord_id})

    if existing:
        # Utente già registrato — controlla stato approvazione
        if existing.get("approvato") == False:
            return templates.TemplateResponse("accesso_negato.html", {
                "request":  request,
                "username": user.get("username", ""),
                "motivo":   "Il tuo account è in attesa di approvazione da parte del Direttore."
            }, status_code=403)
    else:
        # Primo accesso — salva come "in attesa"
        ruolo = get_role_name(role_ids)
        if ruolo == "Direttore":
            categoria = "dirigenza"
            approvato = True  # Il Direttore approva se stesso
        elif ruolo == "Dirigenza":
            categoria = "dirigenza"
            approvato = False
        else:
            categoria = "tirocinio"
            approvato = False

        await db["dipendenti"].insert_one({
            "discord_id":  discord_id,
            "username":    user.get("username"),
            "nome":        nick or user.get("username"),
            "cognome":     "",
            "ruolo":       ruolo,
            "categoria":   categoria,
            "badge":       "—",
            "stato":       "in servizio",
            "approvato":   approvato,
            "sanzioni":    [],
            "note":        "Registrato automaticamente al primo accesso",
            "added_by":    "Sistema",
            "timestamp":   datetime.now().strftime("%d/%m/%Y %H:%M"),
        })

        # Notifica Discord al Direttore
        if not approvato:
            try:
                await notify_direttore(db, discord_id, user.get("username"), ruolo)
            except Exception:
                pass

        if not approvato:
            return templates.TemplateResponse("accesso_negato.html", {
                "request":  request,
                "username": user.get("username", ""),
                "motivo":   "Il tuo account è stato registrato ed è in attesa di approvazione da parte del Direttore."
            }, status_code=403)

    session_data = {
        "discord_id": discord_id,
        "username":   user.get("username"),
        "avatar":     user.get("avatar"),
        "role_ids":   role_ids,
        "permission": permission,
    }
    token = create_session_token(session_data)
    redirect = RedirectResponse(url="/dashboard")
    redirect.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=JWT_EXPIRE_HOURS * 3600,
    )
    return redirect


async def notify_direttore(db, discord_id: str, username: str, ruolo: str):
    """Invia un messaggio Discord al Direttore tramite il bot."""
    import discord as discord_lib
    from bot.cogs import get_bot
    bot = get_bot()
    if not bot:
        return
    guild = bot.get_guild(DISCORD_GUILD_ID)
    if not guild:
        return
    # Trova il Direttore
    from config import ROLE_PERMISSIONS
    direttore_role_id = None
    for rid, lvl in ROLE_PERMISSIONS.items():
        if lvl == 100:
            direttore_role_id = int(rid)
            break
    if not direttore_role_id:
        return
    role = guild.get_role(direttore_role_id)
    if not role:
        return
    for member in role.members:
        try:
            embed = discord_lib.Embed(
                title="🏥 Nuovo accesso in attesa di approvazione",
                color=0xdc2626,
                timestamp=datetime.utcnow(),
            )
            embed.add_field(name="👤 Utente", value=f"{username} (<@{discord_id}>)", inline=False)
            embed.add_field(name="🏷️ Ruolo rilevato", value=ruolo, inline=True)
            embed.add_field(name="✅ Azione richiesta", value="Vai su Gestione Utenti per approvare o rifiutare.", inline=False)
            embed.set_footer(text="Ospedale San Camillo — Gestionale Interno")
            await member.send(embed=embed)
        except Exception:
            pass


@router.get("/logout")
async def logout():
    resp = RedirectResponse(url="/")
    resp.delete_cookie(COOKIE_NAME)
    return resp


def get_current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Non autenticato.")
    try:
        return decode_session_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Sessione scaduta.")


def require_permission(min_level: int):
    def checker(user: dict = Depends(get_current_user)) -> dict:
        if user.get("permission", 0) < min_level:
            raise HTTPException(
                status_code=403,
                detail=f"Accesso negato. Livello richiesto: {min_level}."
            )
        return user
    return checker
