"""agent-mq server — Cloud relay for cross-machine AI session communication.

Storage: RocksDB via rocksdict
API: FastAPI
Metadata: collected for analytics (message content NOT logged)
"""

import json
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from rocksdict import Rdict, Options

# ── Config ──

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = str(DATA_DIR / "mq.rocksdb")
HEARTBEAT_TIMEOUT_SEC = 600  # 10 minutes
VERSION = "0.1.0"

# Column family names
CF_REGISTRY = "registry"
CF_INBOX = "inbox"
CF_DONE = "done"
CF_ANALYTICS = "analytics"

# ── DB Setup ──

db: dict[str, Rdict] = {}


def open_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    opts = Options()
    opts.create_if_missing(True)
    main_db = Rdict(DB_PATH, options=opts)
    cfs = {}
    for cf_name in [CF_REGISTRY, CF_INBOX, CF_DONE, CF_ANALYTICS]:
        try:
            cfs[cf_name] = main_db.get_column_family(cf_name)
        except Exception:
            cfs[cf_name] = main_db.create_column_family(cf_name, opts)
    cfs["_main"] = main_db
    return cfs


def close_db():
    for cf in db.values():
        cf.close()


# ── Helpers ──

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_ts():
    return time.time()


def is_alive(data: dict) -> bool:
    hb = data.get("heartbeat_ts", 0)
    return (now_ts() - hb) < HEARTBEAT_TIMEOUT_SEC


def log_event(event_type: str, tool: str = "", extra: dict | None = None):
    """Log anonymous metadata event. Never logs message content."""
    event = {"event": event_type, "tool": tool, "ts": now_iso()}
    if extra:
        event.update(extra)
    event_id = f"{now_ts():.6f}:{uuid.uuid4().hex[:8]}"
    db[CF_ANALYTICS][event_id] = json.dumps(event)


def inbox_count(session_id: str) -> int:
    prefix = f"{session_id}:"
    return sum(1 for k in db[CF_INBOX].keys() if k.startswith(prefix))


# ── Models ──

class RegisterRequest(BaseModel):
    id: str
    alias: str = ""
    desc: str = ""
    tool: str = "claude-code"


class SendRequest(BaseModel):
    target: str
    message: str
    sender: str = Field(alias="from")
    type: str = "text"
    priority: str = "normal"
    reply_to: str | None = None

    class Config:
        populate_by_name = True


class BroadcastRequest(BaseModel):
    message: str
    sender: str = Field(alias="from")
    type: str = "text"
    priority: str = "normal"

    class Config:
        populate_by_name = True



# ── App ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db
    db = open_db()
    yield
    close_db()


app = FastAPI(
    title="agent-mq",
    version=VERSION,
    description="Cloud relay for cross-machine AI session communication",
    lifespan=lifespan,
)


def resolve_alias(alias: str) -> str | None:
    for key, val in db[CF_REGISTRY].items():
        data = json.loads(val)
        if data.get("alias", "").lower() == alias.lower():
            return data["id"]
    return None


def resolve_target(target: str) -> str:
    if target in db[CF_REGISTRY]:
        return target
    sid = resolve_alias(target)
    if sid:
        return sid
    raise HTTPException(status_code=404, detail=f"Target '{target}' not found")


def store_message(target: str, msg: dict):
    """Store a message in target's inbox."""
    inbox_key = f"{target}:{msg['id']}"
    db[CF_INBOX][inbox_key] = json.dumps(msg)


# ── Routes ──

@app.post("/api/v1/register")
def register(req: RegisterRequest):
    data = {
        "id": req.id,
        "alias": req.alias,
        "desc": req.desc,
        "tool": req.tool,
        "heartbeat": now_iso(),
        "heartbeat_ts": now_ts(),
        "registered_at": now_iso(),
    }
    db[CF_REGISTRY][req.id] = json.dumps(data)
    log_event("register", req.tool)
    return {"status": "ok", "id": req.id, "alias": req.alias}


@app.post("/api/v1/send")
def send(req: SendRequest):
    target = resolve_target(req.target)
    if target not in db[CF_REGISTRY]:
        raise HTTPException(status_code=404, detail=f"Target '{target}' not registered")

    msg = {
        "id": str(uuid.uuid4()),
        "from": req.sender,
        "to": target,
        "payload": req.message,
        "type": req.type,
        "priority": req.priority,
        "ts": now_iso(),
    }
    if req.reply_to:
        msg["reply_to"] = req.reply_to

    store_message(target, msg)
    log_event("send", extra={"msg_type": req.type, "priority": req.priority})
    return {"status": "ok", "id": msg["id"], "to": target}


@app.get("/api/v1/recv/{session_id}")
def recv(session_id: str, peek: bool = False, type: str | None = None):
    prefix = f"{session_id}:"
    messages = []
    keys_to_delete = []

    for key, val in db[CF_INBOX].items():
        if not key.startswith(prefix):
            continue
        msg = json.loads(val)
        if type and msg.get("type", "text") != type:
            continue

        sender_data = db[CF_REGISTRY].get(msg.get("from", ""))
        if sender_data:
            msg["_sender_alias"] = json.loads(sender_data).get("alias", "")

        messages.append(msg)
        if not peek:
            keys_to_delete.append(key)

    for key in keys_to_delete:
        msg_data = db[CF_INBOX][key]
        msg = json.loads(msg_data)
        db[CF_DONE][msg["id"]] = msg_data
        del db[CF_INBOX][key]

    if keys_to_delete:
        log_event("recv", extra={"count": len(keys_to_delete)})

    return messages



@app.post("/api/v1/broadcast")
def broadcast(req: BroadcastRequest):
    sent = 0
    for key, val in db[CF_REGISTRY].items():
        data = json.loads(val)
        sid = data["id"]
        if sid == req.sender or not is_alive(data):
            continue

        msg = {
            "id": str(uuid.uuid4()),
            "from": req.sender,
            "to": sid,
            "payload": req.message,
            "type": req.type,
            "priority": req.priority,
            "ts": now_iso(),
            "broadcast": True,
        }
        store_message(sid, msg)
        sent += 1

    log_event("broadcast", extra={"recipients": sent})
    return {"status": "ok", "sent": sent}


@app.get("/api/v1/sessions")
def list_sessions(alive: bool = False):
    sessions = []
    for key, val in db[CF_REGISTRY].items():
        data = json.loads(val)
        alive_status = is_alive(data)
        if alive and not alive_status:
            continue

        sessions.append({
            "id": data["id"],
            "alias": data.get("alias", ""),
            "desc": data.get("desc", ""),
            "tool": data.get("tool", "unknown"),
            "status": "alive" if alive_status else "stale",
            "pending": inbox_count(data["id"]),
            "heartbeat": data.get("heartbeat", ""),
        })

    return sessions


@app.get("/api/v1/resolve/{alias}")
def resolve(alias: str):
    sid = resolve_alias(alias)
    if not sid:
        raise HTTPException(status_code=404, detail=f"Alias '{alias}' not found")
    return json.loads(db[CF_REGISTRY][sid])


@app.get("/api/v1/status")
def status():
    registry_count = sum(1 for _ in db[CF_REGISTRY].keys())
    alive_count = sum(
        1 for val in db[CF_REGISTRY].values()
        if is_alive(json.loads(val))
    )
    pending_count = sum(1 for _ in db[CF_INBOX].keys())
    done_count = sum(1 for _ in db[CF_DONE].keys())

    return {
        "version": VERSION,
        "sessions": {"total": registry_count, "alive": alive_count},
        "messages": {"pending": pending_count, "delivered": done_count},
    }


@app.post("/api/v1/heartbeat/{session_id}")
def heartbeat(session_id: str):
    raw = db[CF_REGISTRY].get(session_id)
    if not raw:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not registered")
    data = json.loads(raw)
    data["heartbeat"] = now_iso()
    data["heartbeat_ts"] = now_ts()
    db[CF_REGISTRY][session_id] = json.dumps(data)
    return {"status": "ok"}


@app.delete("/api/v1/clean")
def clean(timeout: int = 10):
    timeout_sec = timeout * 60
    cleaned = 0
    keys_to_delete = []

    for key, val in db[CF_REGISTRY].items():
        data = json.loads(val)
        if (now_ts() - data.get("heartbeat_ts", 0)) > timeout_sec:
            keys_to_delete.append((key, data))

    for key, data in keys_to_delete:
        sid = data["id"]
        prefix = f"{sid}:"
        for ik in [k for k in db[CF_INBOX].keys() if k.startswith(prefix)]:
            del db[CF_INBOX][ik]
        del db[CF_REGISTRY][key]
        cleaned += 1

    log_event("clean", extra={"removed": cleaned})
    return {"status": "ok", "cleaned": cleaned}


@app.get("/api/v1/analytics/summary")
def analytics_summary():
    """Aggregated anonymous usage stats."""
    events = {}
    tools = {}
    total = 0
    for key, val in db[CF_ANALYTICS].items():
        event = json.loads(val)
        et = event.get("event", "unknown")
        events[et] = events.get(et, 0) + 1
        tool = event.get("tool", "")
        if tool:
            tools[tool] = tools.get(tool, 0) + 1
        total += 1
    return {"total_events": total, "by_event": events, "by_tool": tools}
