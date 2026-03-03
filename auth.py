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
    """
    Confronta gli ID dei ruoli dell'utente con quelli
    configurati nel .env e restituisce il livello massimo.
    """
    level = 0
    for role_id in role_ids:
        level = max(level, ROLE_PERMISSIONS.get(role_id, 0))
    return level


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
    async with httpx.AsyncClient() as client:
        # Step 1: Token exchange
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

        # Step 2: Profilo utente
        user_res = await client.get(
            f"{DISCORD_API_BASE}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if user_res.status_code != 200:
            raise HTTPException(400, "Impossibile ottenere profilo Discord.")
        user = user_res.json()

        # Step 3: Ruoli nel server (come ID)
        member_res = await client.get(
            f"{DISCORD_API_BASE}/users/@me/guilds/{DISCORD_GUILD_ID}/member",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        role_ids: list[str] = []
        if member_res.status_code == 200:
            role_ids = member_res.json().get("roles", [])

    # Step 4: Calcola permesso confrontando ID direttamente
    permission = calculate_permission(role_ids)

    # Step 5: Blocca accesso se nessun ruolo autorizzato
    if permission == 0:
        return templates.TemplateResponse("accesso_negato.html", {
            "request":  request,
            "username": user.get("username", ""),
            "motivo":   "Il tuo account Discord non ha nessun ruolo autorizzato. Contatta il Direttore."
        }, status_code=403)

    session_data = {
        "discord_id": user["id"],
        "username":   user["username"],
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
