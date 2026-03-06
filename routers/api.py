from fastapi import APIRouter, Depends, HTTPException, Header, Request
from database import get_db
from config import API_KEY
from datetime import datetime

router = APIRouter(prefix="/api/v1", tags=["api"])


def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="API key non valida.")
    return x_api_key


@router.get("/ping")
async def ping(api_key: str = Depends(verify_api_key)):
    return {"status": "ok", "message": "Ospedale San Camillo online.", "timestamp": datetime.now().isoformat()}


@router.get("/ricoverati")
async def get_ricoverati(api_key: str = Depends(verify_api_key), db=Depends(get_db)):
    pazienti = await db["pazienti"].find(
        {"status": {"$in": ["ricoverato", "critico", "in osservazione"]}},
        {"_id": 0, "nome": 1, "cognome": 1, "eta": 1, "diagnosi": 1, "status": 1, "medico_ref": 1, "timestamp": 1}
    ).to_list(100)
    return {"status": "ok", "data": pazienti, "source": "ospedale"}


@router.get("/segnalazioni")
async def get_segnalazioni(api_key: str = Depends(verify_api_key), db=Depends(get_db)):
    items = await db["shared_segnalazioni"].find({}, {"_id": 0}).sort("timestamp", -1).to_list(50)
    return {"status": "ok", "data": items}


@router.post("/segnalazioni")
async def post_segnalazione(request: Request, api_key: str = Depends(verify_api_key), db=Depends(get_db)):
    body = await request.json()
    segnalazione = {
        "tipo":        body.get("tipo", "Generico"),
        "priorita":    body.get("priorita", "media"),
        "descrizione": body.get("descrizione", ""),
        "source":      body.get("source", "esterno"),
        "author":      body.get("author", "Sistema Esterno"),
        "status":      "aperta",
        "timestamp":   datetime.now().strftime("%d/%m/%Y %H:%M"),
    }
    await db["shared_segnalazioni"].insert_one(segnalazione)
    await db["segnalazioni"].insert_one({**segnalazione, "reparto": "Esterno"})
    return {"status": "ok", "message": "Segnalazione ricevuta."}


@router.get("/comunicati")
async def get_comunicati(api_key: str = Depends(verify_api_key), db=Depends(get_db)):
    items = await db["shared_comunicati"].find({}, {"_id": 0}).sort("timestamp", -1).to_list(50)
    return {"status": "ok", "data": items}


@router.post("/comunicati")
async def post_comunicato(request: Request, api_key: str = Depends(verify_api_key), db=Depends(get_db)):
    body = await request.json()
    comunicato = {
        "titolo":      body.get("titolo", ""),
        "contenuto":   body.get("contenuto", ""),
        "priority":    body.get("priority", "normale"),
        "destinatari": body.get("destinatari", "Tutto il personale"),
        "source":      body.get("source", "esterno"),
        "author":      body.get("author", "Sistema Esterno"),
        "timestamp":   datetime.now().strftime("%d/%m/%Y %H:%M"),
    }
    await db["shared_comunicati"].insert_one(comunicato)
    await db["comunicati"].insert_one(comunicato)
    return {"status": "ok", "message": "Comunicato ricevuto."}


@router.get("/trasferimenti")
async def get_trasferimenti(api_key: str = Depends(verify_api_key), db=Depends(get_db)):
    items = await db["shared_trasferimenti"].find({}, {"_id": 0}).sort("timestamp", -1).to_list(50)
    return {"status": "ok", "data": items}


@router.post("/trasferimenti")
async def post_trasferimento(request: Request, api_key: str = Depends(verify_api_key), db=Depends(get_db)):
    body = await request.json()
    trasferimento = {
        "nome":      body.get("nome", ""),
        "cognome":   body.get("cognome", ""),
        "eta":       body.get("eta", ""),
        "motivo":    body.get("motivo", ""),
        "da":        body.get("da", ""),
        "a":         body.get("a", "ospedale"),
        "note":      body.get("note", ""),
        "source":    body.get("source", "esterno"),
        "status":    "in arrivo",
        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }
    await db["shared_trasferimenti"].insert_one(trasferimento)
    if trasferimento["a"] == "ospedale":
        await db["pazienti"].insert_one({
            "nome":          trasferimento["nome"],
            "cognome":       trasferimento["cognome"],
            "eta":           trasferimento["eta"],
            "diagnosi":      trasferimento["motivo"],
            "medico_ref":    "",
            "status":        "in osservazione",
            "note":          f"Trasferito da: {trasferimento['da']} — {trasferimento['note']}",
            "registered_by": "Sistema Esterno",
            "timestamp":     trasferimento["timestamp"],
        })
    return {"status": "ok", "message": "Trasferimento registrato."}
