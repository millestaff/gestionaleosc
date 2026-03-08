import asyncio
import os
from contextlib import asynccontextmanager
import nextcord
import uvicorn
from nextcord.ext import commands
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import config
import database
from auth import router as auth_router
from bot.cogs import setup_bot
from routers.dashboard import router as dashboard_router
from routers.cittadini import router as cittadini_router
from routers.api import router as api_router
from datetime import datetime, timezone

intents = nextcord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(intents=intents)

LOG_CHANNEL_STATUS = 1472932916362346551

# Caricamento Cogs
if os.path.exists("./cogs"):
    for file in os.listdir("./cogs"):
        if file.endswith(".py") and file != "__init__.py":
            try:
                bot.load_extension(f"cogs.{file[:-3]}")
                print(f"Caricato: {file}")
            except Exception as e:
                print(f"Impossibile caricare {file}: {e}")

@bot.event
async def on_ready():
    print(f"✅ Bot connesso come {bot.user}")
    channel = bot.get_channel(LOG_CHANNEL_STATUS)
    if channel:
        embed = nextcord.Embed(
            title="🏥 Sistema Ospedaliero Avviato",
            description="Il bot e il gestionale sono ora online.",
            color=0xdc2626,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="⏰ Orario Avvio", value=f"<t:{int(datetime.now().timestamp())}:F>", inline=False)
        embed.set_footer(text="Ospedale San Camillo — Gestionale Interno")
        await channel.send(embed=embed)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.connect_db()
    db = database.get_db()
    await setup_bot(bot, db)
    yield
    await database.close_db()


app = FastAPI(
    title="Ospedale San Camillo",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(cittadini_router)
app.include_router(api_router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    token = request.cookies.get("session_token")
    if token:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse("login.html", {"request": request})


async def run_bot():
    await bot.start(config.DISCORD_BOT_TOKEN)


async def run_webserver():
    port = int(os.getenv("PORT", config.APP_PORT))
    server_config = uvicorn.Config(
        app=app,
        host=config.APP_HOST,
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(server_config)
    await server.serve()


async def main():
    print("🚀 Avvio Ospedale San Camillo...")
    await asyncio.gather(
        run_bot(),
        run_webserver(),
    )


if __name__ == "__main__":
    asyncio.run(main())
