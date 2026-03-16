"""agent-mq server — Cloud relay for cross-machine AI session communication.

Storage: SQLite (embedded, zero dependencies)
API: FastAPI
Auth: Token-based, per-user data isolation
"""

import json
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# ── Config ──

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = str(DATA_DIR / "mq.db")
VERSION = "0.1.7"
MAX_MESSAGE_BYTES = 10_000  # 10 KB
RATE_LIMIT = "10/second"

# ── DB Setup ──

db: sqlite3.Connection | None = None


def open_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS agents (
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            desc TEXT DEFAULT '',
            tool TEXT DEFAULT 'claude-code',
            registered_at TEXT NOT NULL,
            PRIMARY KEY (user_id, name)
        );
        CREATE TABLE IF NOT EXISTS inbox (
            user_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            msg_id TEXT NOT NULL,
            data TEXT NOT NULL,
            ts TEXT NOT NULL,
            PRIMARY KEY (user_id, agent_name, msg_id)
        );
        CREATE TABLE IF NOT EXISTS done (
            user_id TEXT NOT NULL,
            msg_id TEXT NOT NULL,
            data TEXT NOT NULL,
            ts TEXT NOT NULL,
            PRIMARY KEY (user_id, msg_id)
        );
        CREATE TABLE IF NOT EXISTS analytics (
            id TEXT PRIMARY KEY,
            data TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS counters (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL DEFAULT 0
        );
        INSERT OR IGNORE INTO counters (key, value) VALUES ('users', 0);
        INSERT OR IGNORE INTO counters (key, value) VALUES ('agents', 0);
        INSERT OR IGNORE INTO counters (key, value) VALUES ('messages', 0);
    """)
    conn.commit()
    return conn


def close_db():
    if db:
        db.close()


# ── Helpers ──

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_event(event_type: str, tool: str = "", extra: dict | None = None):
    event = {"event": event_type, "tool": tool, "ts": now_iso()}
    if extra:
        event.update(extra)
    event_id = f"{time.time():.6f}:{uuid.uuid4().hex[:8]}"
    db.execute("INSERT INTO analytics (id, data) VALUES (?, ?)",
               (event_id, json.dumps(event)))
    db.commit()


# ── Auth ──

def get_token(request: Request) -> str:
    """Extract token from header. Auto-register if new."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth[7:]
    if len(token) < 16:
        raise HTTPException(status_code=401, detail="Token too short (min 16 chars)")
    row = db.execute("SELECT 1 FROM users WHERE user_id = ?", (token,)).fetchone()
    if not row:
        db.execute("INSERT INTO users (user_id, created_at) VALUES (?, ?)",
                   (token, now_iso()))
        db.execute("UPDATE counters SET value = value + 1 WHERE key = 'users'")
        db.commit()
    return token


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
app.add_middleware(CORSMiddleware, allow_origins=["https://agent-mq.com"], allow_methods=["GET"], allow_headers=["*"])


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

@app.get("/healthz")
def healthz():
    """Health check — no auth required."""
    db.execute("SELECT 1")
    return {"status": "ok"}


@app.get("/llms.txt")
def llms_txt():
    from starlette.responses import RedirectResponse
    return RedirectResponse("https://agent-mq.com/llms.txt")


@app.post("/api/v1/agents")
@limiter.limit(RATE_LIMIT)
def add_agent(request: Request, req: AgentRequest, user_id: str = Depends(get_token)):
    existing = db.execute("SELECT 1 FROM agents WHERE user_id = ? AND name = ?", (user_id, req.name)).fetchone()
    db.execute(
        "INSERT OR REPLACE INTO agents (user_id, name, desc, tool, registered_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, req.name, req.desc, req.tool, now_iso()))
    if not existing:
        db.execute("UPDATE counters SET value = value + 1 WHERE key = 'agents'")
    db.commit()
    log_event("add_agent", req.tool)
    return {"status": "ok", "name": req.name}


@app.post("/api/v1/send")
@limiter.limit(RATE_LIMIT)
def send(request: Request, req: SendRequest, user_id: str = Depends(get_token)):
    row = db.execute("SELECT 1 FROM agents WHERE user_id = ? AND name = ?",
                     (user_id, req.target)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Target '{req.target}' not found")

    msg = {
        "id": str(uuid.uuid4()),
        "from": req.sender,
        "to": req.target,
        "payload": req.message,
        "type": req.type,
        "priority": req.priority,
        "ts": now_iso(),
    }
    if req.reply_to:
        msg["reply_to"] = req.reply_to

    db.execute("INSERT INTO inbox (user_id, agent_name, msg_id, data, ts) VALUES (?, ?, ?, ?, ?)",
               (user_id, req.target, msg["id"], json.dumps(msg), msg["ts"]))
    db.execute("UPDATE counters SET value = value + 1 WHERE key = 'messages'")
    db.commit()
    log_event("send", extra={"msg_type": req.type, "priority": req.priority})
    return {"status": "ok", "id": msg["id"], "to": req.target}


@app.get("/api/v1/recv")
def recv_all(request: Request, type: str | None = None, user_id: str = Depends(get_token)):
    """Receive all messages across all agents."""
    return _recv(user_id, None, type)


@app.get("/api/v1/recv/{agent_name}")
def recv(agent_name: str, request: Request, type: str | None = None, user_id: str = Depends(get_token)):
    """Receive messages for a specific agent."""
    return _recv(user_id, agent_name, type)


def _recv(user_id: str, agent_name: str | None, type: str | None):
    if agent_name:
        rows = db.execute(
            "SELECT agent_name, msg_id, data FROM inbox WHERE user_id = ? AND agent_name = ? ORDER BY ts",
            (user_id, agent_name)).fetchall()
    else:
        rows = db.execute(
            "SELECT agent_name, msg_id, data FROM inbox WHERE user_id = ? ORDER BY ts",
            (user_id,)).fetchall()

    messages = []
    keys = []
    for r in rows:
        msg = json.loads(r["data"])
        if type and msg.get("type", "text") != type:
            continue
        messages.append(msg)
        keys.append((r["agent_name"], r["msg_id"]))

    for i, (aname, mid) in enumerate(keys):
        db.execute("INSERT INTO done (user_id, msg_id, data, ts) VALUES (?, ?, ?, ?)",
                   (user_id, mid, json.dumps(messages[i]), messages[i].get("ts", "")))
        db.execute("DELETE FROM inbox WHERE user_id = ? AND agent_name = ? AND msg_id = ?",
                   (user_id, aname, mid))
    if keys:
        db.commit()
        log_event("recv", extra={"count": len(keys)})

    return messages


@app.get("/api/v1/agents")
def list_agents(request: Request, user_id: str = Depends(get_token)):
    rows = db.execute("SELECT name, desc, tool FROM agents WHERE user_id = ?", (user_id,)).fetchall()
    agents = []
    for r in rows:
        pending = db.execute(
            "SELECT COUNT(*) as c FROM inbox WHERE user_id = ? AND agent_name = ?",
            (user_id, r["name"])).fetchone()["c"]
        agents.append({
            "name": r["name"],
            "desc": r["desc"],
            "tool": r["tool"],
            "pending": pending,
        })
    return agents


@app.get("/api/v1/agents/{name}")
def get_agent(name: str, request: Request, user_id: str = Depends(get_token)):
    row = db.execute("SELECT * FROM agents WHERE user_id = ? AND name = ?",
                     (user_id, name)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return dict(row)


@app.get("/api/v1/status")
def status(request: Request, user_id: str = Depends(get_token)):
    reg_count = db.execute("SELECT COUNT(*) as c FROM agents WHERE user_id = ?", (user_id,)).fetchone()["c"]
    pending = db.execute("SELECT COUNT(*) as c FROM inbox WHERE user_id = ?", (user_id,)).fetchone()["c"]
    delivered = db.execute("SELECT COUNT(*) as c FROM done WHERE user_id = ?", (user_id,)).fetchone()["c"]
    return {
        "version": VERSION,
        "sessions": {"total": reg_count},
        "messages": {"pending": pending, "delivered": delivered},
    }


@app.get("/api/v1/history")
def history(request: Request, limit: int = 20, user_id: str = Depends(get_token)):
    rows = db.execute("SELECT data FROM done WHERE user_id = ? ORDER BY ts DESC LIMIT ?",
                      (user_id, limit)).fetchall()
    return [json.loads(r["data"]) for r in rows]


@app.get("/api/v1/stats")
def public_stats():
    """Public stats — no auth required. O(1) via counters."""
    rows = db.execute("SELECT key, value FROM counters").fetchall()
    c = {r["key"]: r["value"] for r in rows}
    return {"users": c.get("users", 0), "agents": c.get("agents", 0), "messages": c.get("messages", 0)}


@app.get("/api/v1/analytics/summary")
def analytics_summary(request: Request, user_id: str = Depends(get_token)):
    rows = db.execute("SELECT data FROM analytics").fetchall()
    events = {}
    tools = {}
    total = 0
    for r in rows:
        event = json.loads(r["data"])
        et = event.get("event", "unknown")
        events[et] = events.get(et, 0) + 1
        tool = event.get("tool", "")
        if tool:
            tools[tool] = tools.get(tool, 0) + 1
        total += 1
    return {"total_events": total, "by_event": events, "by_tool": tools}
