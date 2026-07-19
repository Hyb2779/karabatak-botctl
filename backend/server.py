"""BOT.CTL — Ubuntu Telegram Bot Manager (FastAPI)."""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import uuid
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form, Response, Request
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from auth import (
    verify_password,
    create_access_token,
    seed_admin,
    get_current_user,
)
import bot_manager as bm

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="BOT.CTL")
api_router = APIRouter(prefix="/api")
scheduler = AsyncIOScheduler()


# ---------- Models ----------
class LoginRequest(BaseModel):
    username: str
    password: str


class BotUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    auto_restart: Optional[bool] = None
    start_cron: Optional[str] = None
    stop_cron: Optional[str] = None
    entry_file: Optional[str] = None


# ---------- AUTH ----------
@api_router.post("/auth/login")
async def login(payload: LoginRequest, response: Response):
    user = await db.users.find_one({"username": payload.username})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(user["username"])
    response.set_cookie(
        key="access_token", value=token, httponly=True,
        secure=False, samesite="lax", max_age=60 * 60 * 12, path="/",
    )
    return {"username": user["username"], "role": user.get("role", "admin"), "access_token": token}


@api_router.post("/auth/logout")
async def logout(response: Response, _user=Depends(get_current_user)):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@api_router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return user


# ---------- BOTS ----------
@api_router.get("/bots")
async def list_bots(_user=Depends(get_current_user)):
    bots = await db.bots.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return bots


@api_router.get("/bots/{bot_id}")
async def get_bot(bot_id: str, _user=Depends(get_current_user)):
    bot = await db.bots.find_one({"id": bot_id}, {"_id": 0})
    if not bot:
        raise HTTPException(404, "Bot not found")
    return {"bot": bot, "stats": bm.get_stats(bot_id)}


@api_router.get("/bots/{bot_id}/stats")
async def bot_stats(bot_id: str, _user=Depends(get_current_user)):
    bot = await db.bots.find_one({"id": bot_id})
    if not bot:
        raise HTTPException(404, "Bot not found")
    return bm.get_stats(bot_id)


@api_router.post("/bots")
async def create_bot(
    name: str = Form(...),
    description: str = Form(""),
    auto_restart: bool = Form(False),
    entry_file: str = Form(""),
    file: UploadFile = File(...),
    _user=Depends(get_current_user),
):
    """Create a bot from either a single .py file or a .zip archive (folder of files)."""
    fname = (file.filename or "").lower()
    bot_id = str(uuid.uuid4())
    content = await file.read()

    if fname.endswith(".zip"):
        py_files = bm.extract_zip_to_bot(bot_id, content)
        if not py_files:
            await bm.delete_bot_files(bot_id)
            raise HTTPException(400, "Zip içinde .py dosyası bulunamadı")
        # Pick entry: user-specified, single, or root-level single
        if entry_file:
            if entry_file not in py_files:
                await bm.delete_bot_files(bot_id)
                raise HTTPException(400, f"entry_file '{entry_file}' bulunamadı. .py dosyaları: {py_files}")
            chosen = entry_file
        elif len(py_files) == 1:
            chosen = py_files[0]
        else:
            # If exactly one .py at the root, use it
            roots = [p for p in py_files if "/" not in p]
            if len(roots) == 1:
                chosen = roots[0]
            else:
                # Keep files but return 409 with the choices
                doc = {
                    "id": bot_id,
                    "name": name.strip(),
                    "description": description.strip(),
                    "entry_file": "",  # to be set by user
                    "auto_restart": bool(auto_restart),
                    "user_stopped": True,
                    "start_cron": None,
                    "stop_cron": None,
                    "last_started_at": None,
                    "last_pid": None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                await db.bots.insert_one(doc)
                doc.pop("_id", None)
                doc["needs_entry_selection"] = True
                doc["py_files"] = py_files
                return doc
        chosen_file = chosen
    elif fname.endswith(".py"):
        chosen_file = bm.write_single_py(bot_id, file.filename, content)
    else:
        raise HTTPException(400, "Sadece .py veya .zip dosyaları kabul edilir")

    doc = {
        "id": bot_id,
        "name": name.strip() or chosen_file,
        "description": description.strip(),
        "entry_file": chosen_file,
        "auto_restart": bool(auto_restart),
        "user_stopped": True,
        "start_cron": None,
        "stop_cron": None,
        "last_started_at": None,
        "last_pid": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.bots.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.put("/bots/{bot_id}")
async def update_bot(bot_id: str, payload: BotUpdate, _user=Depends(get_current_user)):
    bot = await db.bots.find_one({"id": bot_id})
    if not bot:
        raise HTTPException(404, "Bot not found")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}

    # Validate entry_file exists if changing
    if "entry_file" in updates:
        py = bm.list_py_files(bot_id)
        if updates["entry_file"] not in py:
            raise HTTPException(400, f"entry_file '{updates['entry_file']}' mevcut değil")

    if updates:
        await db.bots.update_one({"id": bot_id}, {"$set": updates})

    if "start_cron" in updates or "stop_cron" in updates or "entry_file" in updates:
        bot = await db.bots.find_one({"id": bot_id})
        bm.schedule_bot(bot_id, bot["entry_file"], bot.get("start_cron"), bot.get("stop_cron"))

    bot = await db.bots.find_one({"id": bot_id}, {"_id": 0})
    return bot


@api_router.get("/bots/{bot_id}/files")
async def list_bot_files(bot_id: str, _user=Depends(get_current_user)):
    bot = await db.bots.find_one({"id": bot_id})
    if not bot:
        raise HTTPException(404, "Bot not found")
    return {"files": bm.list_files(bot_id), "py_files": bm.list_py_files(bot_id)}


@api_router.post("/bots/{bot_id}/files")
async def upload_bot_file(
    bot_id: str,
    file: UploadFile = File(...),
    dest_dir: str = Form(""),
    _user=Depends(get_current_user),
):
    bot = await db.bots.find_one({"id": bot_id})
    if not bot:
        raise HTTPException(404, "Bot not found")
    content = await file.read()
    rel = bm.add_file(bot_id, file.filename, content, dest_dir)
    return {"ok": True, "path": rel}


@api_router.delete("/bots/{bot_id}/files")
async def delete_bot_file(bot_id: str, path: str, _user=Depends(get_current_user)):
    bot = await db.bots.find_one({"id": bot_id})
    if not bot:
        raise HTTPException(404, "Bot not found")
    if bot.get("entry_file") == path:
        raise HTTPException(400, "Önce entry_file'ı değiştir, sonra sil")
    try:
        bm.delete_file(bot_id, path)
    except ValueError:
        raise HTTPException(400, "Geçersiz yol")
    return {"ok": True}


@api_router.delete("/bots/{bot_id}")
async def delete_bot(bot_id: str, _user=Depends(get_current_user)):
    bot = await db.bots.find_one({"id": bot_id})
    if not bot:
        raise HTTPException(404, "Bot not found")
    await bm.stop_bot(bot_id, _auto_called=True)
    bm.unschedule_bot(bot_id)
    await bm.delete_bot_files(bot_id)
    await db.bots.delete_one({"id": bot_id})
    return {"ok": True}


@api_router.post("/bots/{bot_id}/start")
async def start_bot_api(bot_id: str, _user=Depends(get_current_user)):
    bot = await db.bots.find_one({"id": bot_id})
    if not bot:
        raise HTTPException(404, "Bot not found")
    if not bot.get("entry_file"):
        raise HTTPException(400, "Bot için entry_file seçilmemiş")
    await db.bots.update_one({"id": bot_id}, {"$set": {"user_stopped": False}})
    return await bm.start_bot(bot_id, bot["entry_file"])


@api_router.post("/bots/{bot_id}/stop")
async def stop_bot_api(bot_id: str, _user=Depends(get_current_user)):
    return await bm.stop_bot(bot_id)


@api_router.post("/bots/{bot_id}/restart")
async def restart_bot_api(bot_id: str, _user=Depends(get_current_user)):
    bot = await db.bots.find_one({"id": bot_id})
    if not bot:
        raise HTTPException(404, "Bot not found")
    if not bot.get("entry_file"):
        raise HTTPException(400, "Bot için entry_file seçilmemiş")
    return await bm.restart_bot(bot_id, bot["entry_file"])


@api_router.get("/bots/{bot_id}/logs")
async def bot_logs(bot_id: str, lines: int = 300, _user=Depends(get_current_user)):
    return {"logs": bm.read_logs(bot_id, lines=lines)}


@api_router.post("/bots/{bot_id}/logs/clear")
async def clear_bot_logs(bot_id: str, _user=Depends(get_current_user)):
    bm.clear_logs(bot_id)
    return {"ok": True}


@api_router.get("/system/stats")
async def system_stats(_user=Depends(get_current_user)):
    import psutil
    bots = await db.bots.find({}).to_list(500)
    total_cpu = 0.0
    total_ram_mb = 0.0
    running = 0
    for b in bots:
        s = bm.get_stats(b["id"])
        if s["status"] == "running":
            running += 1
            total_cpu += s["cpu"]
            total_ram_mb += s["ram_mb"]
    return {
        "total_bots": len(bots),
        "running_bots": running,
        "total_cpu_percent": round(total_cpu, 1),
        "total_ram_mb": round(total_ram_mb, 1),
        "system_cpu_percent": round(psutil.cpu_percent(interval=None), 1),
        "system_ram_percent": round(psutil.virtual_memory().percent, 1),
    }


# ---------- App wiring ----------
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("botctl")


@app.on_event("startup")
async def startup():
    await db.users.create_index("username", unique=True)
    await db.bots.create_index("id", unique=True)
    await seed_admin(db)

    bm.init_manager(db, scheduler)
    scheduler.start()

    async for bot in db.bots.find({}):
        if bot.get("entry_file"):
            bm.schedule_bot(bot["id"], bot["entry_file"],
                            bot.get("start_cron"), bot.get("stop_cron"))

    asyncio.create_task(bm.watcher_loop())
    logger.info("BOT.CTL started, scheduler + watcher active")


@app.on_event("shutdown")
async def shutdown():
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass
    for bot_id in list(bm._running.keys()):
        await bm.stop_bot(bot_id, _auto_called=True)
    client.close()
