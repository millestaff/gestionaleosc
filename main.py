import asyncio
from contextlib import asynccontextmanager

import discord
import uvicorn
from discord.ext import commands
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config
import database
from auth import router as auth_router
from bot.cogs import setup_bot
from routers.dashboard import router as dashboard_router

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"[Bot] Connesso come {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"[Bot] {len(synced)} slash commands sincronizzati.")
    except Exception as e:
        print(f"[Bot] Errore sync slash: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.connect_db()
    db = database.get_db()
    await setup_bot(bot, db)
    yield
    await database.close_db()


app = FastAPI(
    title="Gestionale Polizia",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(auth_router)
app.include_router(dashboard_router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    token = request.cookies.get("session_token")
    if token:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse("login.html", {"request": request})


async def run_bot():
    async with bot:
        await bot.start(config.DISCORD_BOT_TOKEN)


async def run_webserver():
    server_config = uvicorn.Config(
        app=app,
        host=config.APP_HOST,
        port=config.APP_PORT,
        log_level="info",
    )
    server = uvicorn.Server(server_config)
    await server.serve()


async def main():
    print("🚀 Avvio Gestionale Polizia FiveM...")
    await asyncio.gather(
        run_bot(),
        run_webserver(),
    )


if __name__ == "__main__":
    asyncio.run(main())
