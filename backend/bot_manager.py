"""Bot process management: start, stop, restart, monitor, schedule, auto-restart.

Supports multi-file bot projects (uploaded as .zip or .py).
"""
import os
import sys
import asyncio
import signal
import zipfile
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
import psutil
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

BOT_STORAGE_DIR = Path(os.environ.get("BOT_STORAGE_DIR", "/app/bot_storage"))
BOTS_DIR = BOT_STORAGE_DIR / "bots"
LOGS_DIR = BOT_STORAGE_DIR / "logs"
BOTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# In-memory pid registry: bot_id -> {"process": Popen, "started_at": iso, "log_file": file}
_running: Dict[str, Dict[str, Any]] = {}

scheduler: Optional[AsyncIOScheduler] = None
_db = None


def init_manager(db, sched: AsyncIOScheduler):
    global _db, scheduler
    _db = db
    scheduler = sched


def bot_dir(bot_id: str) -> Path:
    d = BOTS_DIR / bot_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def bot_log_path(bot_id: str) -> Path:
    return LOGS_DIR / f"{bot_id}.log"


# ---------- FILE OPERATIONS ----------

def _safe_join(base: Path, rel: str) -> Path:
    """Join paths safely, preventing directory traversal."""
    target = (base / rel).resolve()
    if not str(target).startswith(str(base.resolve())):
        raise ValueError("path escapes bot directory")
    return target


def extract_zip_to_bot(bot_id: str, zip_bytes: bytes) -> List[str]:
    """Extract zip bytes into bot dir, return list of .py files (relative paths)."""
    bdir = bot_dir(bot_id)
    tmp_zip = bdir / "_upload.zip"
    tmp_zip.write_bytes(zip_bytes)

    py_files: List[str] = []
    with zipfile.ZipFile(tmp_zip) as zf:
        # detect a common top-level folder to strip (e.g., "kod botu/")
        names = [n for n in zf.namelist() if not n.startswith("__MACOSX") and not n.endswith("/")]
        if not names:
            tmp_zip.unlink()
            return []
        top_parts = {n.split("/", 1)[0] for n in names}
        strip_prefix = ""
        if len(top_parts) == 1:
            only = list(top_parts)[0]
            # only strip if everything has a / after it (i.e., it IS a folder)
            if all(n == only or n.startswith(only + "/") for n in names):
                strip_prefix = only + "/"

        for name in names:
            if name.startswith("__MACOSX") or name.endswith(".DS_Store"):
                continue
            rel = name[len(strip_prefix):] if strip_prefix and name.startswith(strip_prefix) else name
            if not rel:
                continue
            # Reject path traversal
            target = _safe_join(bdir, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(name) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            if rel.endswith(".py"):
                py_files.append(rel)
    tmp_zip.unlink()
    return py_files


def write_single_py(bot_id: str, filename: str, content: bytes) -> str:
    bdir = bot_dir(bot_id)
    safe = os.path.basename(filename)
    dest = bdir / safe
    dest.write_bytes(content)
    return safe


def list_files(bot_id: str) -> List[Dict[str, Any]]:
    """Recursively list files in bot dir, return list of {path, size, is_py}."""
    bdir = bot_dir(bot_id)
    out = []
    for root, _, files in os.walk(bdir):
        for f in files:
            full = Path(root) / f
            rel = str(full.relative_to(bdir))
            try:
                size = full.stat().st_size
            except Exception:
                size = 0
            out.append({"path": rel, "size": size, "is_py": rel.endswith(".py")})
    out.sort(key=lambda x: x["path"])
    return out


def list_py_files(bot_id: str) -> List[str]:
    return [f["path"] for f in list_files(bot_id) if f["is_py"]]


def delete_file(bot_id: str, rel_path: str):
    bdir = bot_dir(bot_id)
    target = _safe_join(bdir, rel_path)
    if target.exists() and target.is_file():
        target.unlink()


def add_file(bot_id: str, filename: str, content: bytes, dest_rel_dir: str = ""):
    bdir = bot_dir(bot_id)
    safe_name = os.path.basename(filename)
    target_dir = _safe_join(bdir, dest_rel_dir) if dest_rel_dir else bdir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe_name
    target.write_bytes(content)
    return str(target.relative_to(bdir))


# ---------- PROCESS LIFECYCLE ----------

def is_running(bot_id: str) -> bool:
    entry = _running.get(bot_id)
    if not entry:
        return False
    proc: subprocess.Popen = entry["process"]
    return proc.poll() is None


def get_stats(bot_id: str) -> Dict[str, Any]:
    entry = _running.get(bot_id)
    if not entry or entry["process"].poll() is not None:
        return {"status": "stopped", "pid": None, "cpu": 0.0, "ram_mb": 0.0, "uptime": 0}
    proc: subprocess.Popen = entry["process"]
    pid = proc.pid
    try:
        p = psutil.Process(pid)
        with p.oneshot():
            cpu = p.cpu_percent(interval=None)
            ram_mb = p.memory_info().rss / (1024 * 1024)
        # include children
        for child in p.children(recursive=True):
            try:
                with child.oneshot():
                    cpu += child.cpu_percent(interval=None)
                    ram_mb += child.memory_info().rss / (1024 * 1024)
            except psutil.NoSuchProcess:
                continue
        started_at = datetime.fromisoformat(entry["started_at"])
        uptime = (datetime.now(timezone.utc) - started_at).total_seconds()
        return {
            "status": "running",
            "pid": pid,
            "cpu": round(cpu, 1),
            "ram_mb": round(ram_mb, 1),
            "uptime": int(uptime),
        }
    except psutil.NoSuchProcess:
        return {"status": "stopped", "pid": None, "cpu": 0.0, "ram_mb": 0.0, "uptime": 0}


async def start_bot(bot_id: str, entry_file: str, python_bin: Optional[str] = None) -> Dict[str, Any]:
    if is_running(bot_id):
        return {"ok": True, "message": "already_running", "stats": get_stats(bot_id)}

    bdir = bot_dir(bot_id)
    entry_path = bdir / entry_file
    if not entry_path.exists():
        return {"ok": False, "message": f"entry file not found: {entry_file}"}

    log_path = bot_log_path(bot_id)
    log_f = open(log_path, "ab", buffering=0)
    log_f.write(f"\n----- STARTED {datetime.now(timezone.utc).isoformat()} -----\n".encode())

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    # Run from the entry file's parent dir, in case bot uses relative paths
    cwd = entry_path.parent

    # Use the same python interpreter that runs the backend so bots inherit the
    # same installed packages (telethon, python-telegram-bot, etc.)
    py = python_bin or sys.executable or "python3"

    proc = subprocess.Popen(
        [py, "-u", str(entry_path)],
        cwd=str(cwd),
        stdout=log_f,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
    )
    _running[bot_id] = {
        "process": proc,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "log_file": log_f,
    }
    await _db.bots.update_one(
        {"id": bot_id},
        {"$set": {"last_started_at": _running[bot_id]["started_at"], "last_pid": proc.pid}},
    )
    return {"ok": True, "message": "started", "stats": get_stats(bot_id)}


async def stop_bot(bot_id: str, _auto_called: bool = False) -> Dict[str, Any]:
    entry = _running.get(bot_id)
    if not entry or entry["process"].poll() is not None:
        _running.pop(bot_id, None)
        return {"ok": True, "message": "not_running"}
    proc: subprocess.Popen = entry["process"]
    if not _auto_called:
        await _db.bots.update_one({"id": bot_id}, {"$set": {"user_stopped": True}})
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=4)

    log_f = entry.get("log_file")
    if log_f:
        try:
            log_f.write(f"\n----- STOPPED {datetime.now(timezone.utc).isoformat()} -----\n".encode())
            log_f.close()
        except Exception:
            pass
    _running.pop(bot_id, None)
    return {"ok": True, "message": "stopped"}


async def restart_bot(bot_id: str, entry_file: str) -> Dict[str, Any]:
    await stop_bot(bot_id, _auto_called=True)
    await _db.bots.update_one({"id": bot_id}, {"$set": {"user_stopped": False}})
    return await start_bot(bot_id, entry_file)


async def delete_bot_files(bot_id: str):
    bdir = BOTS_DIR / bot_id
    if bdir.exists():
        shutil.rmtree(bdir, ignore_errors=True)
    log = bot_log_path(bot_id)
    if log.exists():
        try:
            log.unlink()
        except Exception:
            pass


# ---------- LOGS ----------

def read_logs(bot_id: str, lines: int = 300) -> str:
    log = bot_log_path(bot_id)
    if not log.exists():
        return ""
    try:
        with open(log, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            block = 8192
            data = b""
            while size > 0 and data.count(b"\n") <= lines:
                read_size = min(block, size)
                size -= read_size
                f.seek(size)
                data = f.read(read_size) + data
            text = data.decode("utf-8", errors="replace")
            return "\n".join(text.splitlines()[-lines:])
    except Exception as e:
        return f"<log read error: {e}>"


def clear_logs(bot_id: str):
    log = bot_log_path(bot_id)
    if log.exists():
        with open(log, "wb"):
            pass


# ---------- AUTO RESTART WATCHER ----------

async def watcher_loop():
    while True:
        try:
            if _db is not None:
                cursor = _db.bots.find({"auto_restart": True, "user_stopped": {"$ne": True}})
                async for bot in cursor:
                    bid = bot["id"]
                    if not is_running(bid):
                        await start_bot(bid, bot["entry_file"])
        except Exception as e:
            print(f"[watcher] error: {e}")
        await asyncio.sleep(5)


# ---------- SCHEDULING ----------

def _job_id(bot_id: str, action: str) -> str:
    return f"{bot_id}:{action}"


def schedule_bot(bot_id: str, entry_file: str, start_cron: Optional[str], stop_cron: Optional[str]):
    if scheduler is None:
        return
    for action in ("start", "stop"):
        jid = _job_id(bot_id, action)
        if scheduler.get_job(jid):
            scheduler.remove_job(jid)

    async def _start_job():
        await _db.bots.update_one({"id": bot_id}, {"$set": {"user_stopped": False}})
        await start_bot(bot_id, entry_file)

    async def _stop_job():
        await stop_bot(bot_id, _auto_called=False)

    if start_cron:
        try:
            scheduler.add_job(_start_job, CronTrigger.from_crontab(start_cron),
                              id=_job_id(bot_id, "start"), replace_existing=True)
        except Exception as e:
            print(f"[schedule] invalid start_cron for {bot_id}: {e}")
    if stop_cron:
        try:
            scheduler.add_job(_stop_job, CronTrigger.from_crontab(stop_cron),
                              id=_job_id(bot_id, "stop"), replace_existing=True)
        except Exception as e:
            print(f"[schedule] invalid stop_cron for {bot_id}: {e}")


def unschedule_bot(bot_id: str):
    if scheduler is None:
        return
    for action in ("start", "stop"):
        jid = _job_id(bot_id, action)
        if scheduler.get_job(jid):
            scheduler.remove_job(jid)
