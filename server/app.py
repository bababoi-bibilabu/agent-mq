"""agent-mq server — Cloud relay for cross-machine AI session communication.

Storage: RocksDB via rocksdict
API: FastAPI
Auth: Token-based, per-user data isolation
"""

import json
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, Depends
from pydantic import BaseModel, Field
from rocksdict import Rdict, Options
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# ── Config ──

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = str(DATA_DIR / "mq.rocksdb")
VERSION = "0.1.0"
MAX_MESSAGE_BYTES = 10_000  # 10 KB
RATE_LIMIT = "10/second"

# Column family names
CF_USERS = "users"
CF_REGISTRY = "registry"  # key: user_id:agent_id
CF_INBOX = "inbox"         # key: user_id:agent_id:msg_id
CF_DONE = "done"           # key: user_id:msg_id
CF_ANALYTICS = "analytics"

# ── DB Setup ──

db: dict[str, Rdict] = {}


def open_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    opts = Options()
    opts.create_if_missing(True)
    main_db = Rdict(DB_PATH, options=opts)
    cfs = {}
    for cf_name in [CF_USERS, CF_REGISTRY, CF_INBOX, CF_DONE, CF_ANALYTICS]:
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


def log_event(event_type: str, tool: str = "", extra: dict | None = None):
    event = {"event": event_type, "tool": tool, "ts": now_iso()}
    if extra:
        event.update(extra)
    event_id = f"{now_ts():.6f}:{uuid.uuid4().hex[:8]}"
    db[CF_ANALYTICS][event_id] = json.dumps(event)


# ── Auth ──

def get_user_id(request: Request) -> str:
    """Extract and validate token, return user_id."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth[7:]
    user_data = db[CF_USERS].get(token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid token")
    return json.loads(user_data)["user_id"]


# ── User-scoped helpers ──

def _reg_key(user_id: str, agent_id: str) -> str:
    return f"{user_id}:{agent_id}"


def _inbox_key(user_id: str, agent_id: str, msg_id: str) -> str:
    return f"{user_id}:{agent_id}:{msg_id}"


def _done_key(user_id: str, msg_id: str) -> str:
    return f"{user_id}:{msg_id}"


def _user_prefix(user_id: str) -> str:
    return f"{user_id}:"


def resolve_target(user_id: str, target: str) -> str:
    if db[CF_REGISTRY].get(_reg_key(user_id, target)):
        return target
    raise HTTPException(status_code=404, detail=f"Target '{target}' not found")


def store_message(user_id: str, target: str, msg: dict):
    key = _inbox_key(user_id, target, msg["id"])
    db[CF_INBOX][key] = json.dumps(msg)


def inbox_count(user_id: str, agent_id: str) -> int:
    prefix = _inbox_key(user_id, agent_id, "")
    return sum(1 for k in db[CF_INBOX].keys() if k.startswith(prefix))


# ── Models ──

class AgentRequest(BaseModel):
    name: str
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


# ── App ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db
    db = open_db()
    yield
    close_db()


limiter = Limiter(key_func=get_remote_address, default_limits=[RATE_LIMIT])

app = FastAPI(
    title="agent-mq",
    version=VERSION,
    description="Cloud relay for cross-machine AI session communication",
    lifespan=lifespan,
)
app.state.limiter = limiter


def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return Response(
        content=json.dumps({"detail": "Rate limit exceeded"}),
        status_code=429,
        media_type="application/json",
    )


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)


@app.middleware("http")
async def check_body_size(request: Request, call_next):
    if request.method == "POST":
        body = await request.body()
        if len(body) > MAX_MESSAGE_BYTES:
            return Response(
                content=json.dumps({"detail": f"Request body exceeds {MAX_MESSAGE_BYTES} bytes"}),
                status_code=413,
                media_type="application/json",
            )
    return await call_next(request)


# ── Routes ──

@app.post("/api/v1/register")
@limiter.limit(RATE_LIMIT)
def register_account(request: Request):
    """Create a new account. Returns a token."""
    token = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    db[CF_USERS][token] = json.dumps({"user_id": user_id, "created_at": now_iso()})
    log_event("register_account")
    return {"token": token}


@app.post("/api/v1/agents")
@limiter.limit(RATE_LIMIT)
def add_agent(request: Request, req: AgentRequest, user_id: str = Depends(get_user_id)):
    data = {
        "name": req.name,
        "desc": req.desc,
        "tool": req.tool,
        "registered_at": now_iso(),
    }
    db[CF_REGISTRY][_reg_key(user_id, req.name)] = json.dumps(data)
    log_event("add_agent", req.tool)
    return {"status": "ok", "name": req.name}


@app.post("/api/v1/send")
@limiter.limit(RATE_LIMIT)
def send(request: Request, req: SendRequest, user_id: str = Depends(get_user_id)):
    target = resolve_target(user_id, req.target)

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

    store_message(user_id, target, msg)
    log_event("send", extra={"msg_type": req.type, "priority": req.priority})
    return {"status": "ok", "id": msg["id"], "to": target}


@app.get("/api/v1/recv/{agent_id}")
def recv(agent_id: str, request: Request, peek: bool = False, type: str | None = None, user_id: str = Depends(get_user_id)):
    prefix = _inbox_key(user_id, agent_id, "")
    messages = []
    keys_to_delete = []

    for key, val in db[CF_INBOX].items():
        if not key.startswith(prefix):
            continue
        msg = json.loads(val)
        if type and msg.get("type", "text") != type:
            continue

        messages.append(msg)
        if not peek:
            keys_to_delete.append(key)

    for key in keys_to_delete:
        msg_data = db[CF_INBOX][key]
        msg = json.loads(msg_data)
        db[CF_DONE][_done_key(user_id, msg["id"])] = msg_data
        del db[CF_INBOX][key]

    if keys_to_delete:
        log_event("recv", extra={"count": len(keys_to_delete)})

    return messages


@app.get("/api/v1/agents")
def list_agents(request: Request, user_id: str = Depends(get_user_id)):
    prefix = _user_prefix(user_id)
    agents = []
    for key, val in db[CF_REGISTRY].items():
        if not key.startswith(prefix):
            continue
        data = json.loads(val)
        agents.append({
            "name": data["name"],
            "desc": data.get("desc", ""),
            "tool": data.get("tool", "unknown"),
            "pending": inbox_count(user_id, data["name"]),
        })
    return agents


@app.get("/api/v1/agents/{name}")
def get_agent(name: str, request: Request, user_id: str = Depends(get_user_id)):
    raw = db[CF_REGISTRY].get(_reg_key(user_id, name))
    if not raw:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return json.loads(raw)


@app.get("/api/v1/status")
def status(request: Request, user_id: str = Depends(get_user_id)):
    prefix = _user_prefix(user_id)
    reg_count = sum(1 for k in db[CF_REGISTRY].keys() if k.startswith(prefix))
    pending_count = sum(1 for k in db[CF_INBOX].keys() if k.startswith(prefix))
    done_count = sum(1 for k in db[CF_DONE].keys() if k.startswith(prefix))

    return {
        "version": VERSION,
        "sessions": {"total": reg_count},
        "messages": {"pending": pending_count, "delivered": done_count},
    }


@app.get("/api/v1/history")
def history(request: Request, limit: int = 20, user_id: str = Depends(get_user_id)):
    prefix = _user_prefix(user_id)
    messages = []
    for key, val in db[CF_DONE].items():
        if not key.startswith(prefix):
            continue
        messages.append(json.loads(val))
    messages.sort(key=lambda m: m.get("ts", ""), reverse=True)
    return messages[:limit]


@app.get("/api/v1/analytics/summary")
def analytics_summary(request: Request, user_id: str = Depends(get_user_id)):
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
