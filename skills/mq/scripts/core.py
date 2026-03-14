"""agent-mq core — shared logic for MCP server and CLI.

Returns structured data (dict/list). Raises on errors.
Handles both local (file-based) and cloud (HTTP relay) modes.
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

VERSION = "0.1.0"

# ── Config ──

CONFIG_DIR = Path.home() / ".agent-mq"
CONFIG_FILE = CONFIG_DIR / "config.json"

MQ_DIR = Path(os.environ.get("AGENT_MQ_DATA_DIR", str(Path.home() / ".claude" / "mq")))
REGISTRY_DIR = MQ_DIR / "registry"
INBOX_DIR = MQ_DIR / "inbox"
DONE_DIR = MQ_DIR / "done"
HEARTBEAT_TIMEOUT_MIN = 10

MSG_TYPES = ("text", "task", "query", "response", "status")
PRIORITIES = ("low", "normal", "urgent")


def load_config():
    cfg = {"mode": "local", "server": "", "token": ""}
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
    cfg["server"] = cfg.get("server", "").rstrip("/")
    return cfg


def save_config(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def is_cloud():
    return load_config()["mode"] == "cloud"


# ── Cloud transport ──

def _api(method, path, body=None):
    cfg = load_config()
    server = cfg["server"]
    token = cfg["token"]
    if not server:
        raise RuntimeError("Server URL not configured. Run `mq login` first.")

    url = f"{server}/api/v1{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        err = {}
        if e.headers.get("content-type", "").startswith("application/json"):
            err = json.loads(e.read().decode())
        raise RuntimeError(err.get("detail", e.reason))
    except URLError as e:
        raise RuntimeError(f"Cannot reach server: {e.reason}")


# ── Local helpers ──

def _ensure_dirs():
    for d in [REGISTRY_DIR, INBOX_DIR, DONE_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s):
    s = s.rstrip("Z")
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _load_registry():
    _ensure_dirs()
    result = {}
    for f in REGISTRY_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            result[data["id"]] = data
        except (json.JSONDecodeError, KeyError):
            pass
    return result


def _resolve_alias(alias):
    for sid, data in _load_registry().items():
        if data.get("alias", "").lower() == alias.lower():
            return sid, data
    return None, None


def _sanitize_id(session_id):
    """Reject path traversal in session IDs."""
    if "/" in session_id or "\\" in session_id or ".." in session_id or "\0" in session_id:
        raise ValueError(f"Invalid session ID: {session_id!r}")
    return session_id


def _resolve_target(target):
    if len(target) > 20 and "-" in target:
        return _sanitize_id(target)
    sid, _ = _resolve_alias(target)
    return _sanitize_id(sid if sid else target)


def _is_alive(data):
    try:
        hb = _parse_iso(data["heartbeat"])
        return (datetime.now(timezone.utc) - hb) < timedelta(minutes=HEARTBEAT_TIMEOUT_MIN)
    except (KeyError, ValueError):
        return False


# ── Core operations ──

def register(session_id, alias="", desc="", tool="claude-code"):
    """Register a session."""
    _sanitize_id(session_id)
    if is_cloud():
        return _api("POST", "/register", {
            "id": session_id, "alias": alias, "desc": desc, "tool": tool,
        })

    _ensure_dirs()
    (INBOX_DIR / session_id).mkdir(exist_ok=True)
    now = _now_iso()
    data = {
        "id": session_id, "alias": alias, "desc": desc,
        "tool": tool, "heartbeat": now,
        "registered_at": now, "version": VERSION,
    }
    (REGISTRY_DIR / f"{session_id}.json").write_text(json.dumps(data, indent=2))
    return {"status": "ok", "id": session_id, "alias": alias}


def send(target, message, sender, msg_type="text", priority="normal", reply_to=None):
    """Send a message to a target session (ID or alias)."""
    if msg_type not in MSG_TYPES:
        raise ValueError(f"Invalid type '{msg_type}'")
    if priority not in PRIORITIES:
        raise ValueError(f"Invalid priority '{priority}'")

    if is_cloud():
        body = {
            "target": target, "message": message, "from": sender,
            "type": msg_type, "priority": priority,
        }
        if reply_to:
            body["reply_to"] = reply_to
        return _api("POST", "/send", body)

    _ensure_dirs()
    registry = _load_registry()

    # Resolve target using already-loaded registry
    resolved = target
    if not (len(target) > 20 and "-" in target):
        for sid, data in registry.items():
            if data.get("alias", "").lower() == target.lower():
                resolved = sid
                break
    _sanitize_id(resolved)

    target_inbox = INBOX_DIR / resolved
    if not target_inbox.exists():
        raise RuntimeError(f"Target '{target}' not found")

    msg = {
        "id": str(uuid.uuid4()), "from": sender, "to": resolved,
        "payload": message, "type": msg_type, "priority": priority, "ts": _now_iso(),
    }
    if reply_to:
        msg["reply_to"] = reply_to

    tmp = target_inbox / f"{msg['id']}.tmp"
    tmp.write_text(json.dumps(msg, indent=2))
    tmp.rename(target_inbox / f"{msg['id']}.json")

    label = registry.get(resolved, {}).get("alias", "") or resolved[:12] + "..."
    return {"status": "ok", "id": msg["id"], "to": resolved, "label": label}


def recv(session_id, peek=False, msg_type=None):
    """Receive messages from a session's inbox."""
    _sanitize_id(session_id)
    if is_cloud():
        params = f"?peek={'true' if peek else 'false'}"
        if msg_type:
            params += f"&type={msg_type}"
        return _api("GET", f"/recv/{session_id}{params}")

    _ensure_dirs()
    inbox = INBOX_DIR / session_id
    if not inbox.exists():
        return []

    files = sorted(inbox.glob("*.json"), key=lambda f: f.stat().st_mtime)
    if not files:
        return []

    registry = _load_registry()
    messages = []
    for f in files:
        try:
            msg = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        if msg_type and msg.get("type", "text") != msg_type:
            continue
        msg["_sender_alias"] = registry.get(msg.get("from", ""), {}).get("alias", "")
        messages.append(msg)
        if not peek:
            f.rename(DONE_DIR / f.name)

    return messages


def broadcast(message, sender, msg_type="text", priority="normal"):
    """Broadcast a message to all alive sessions."""
    if is_cloud():
        return _api("POST", "/broadcast", {
            "message": message, "from": sender, "type": msg_type, "priority": priority,
        })

    _ensure_dirs()
    registry = _load_registry()
    sent = 0
    for sid, data in registry.items():
        if sid == sender or not _is_alive(data):
            continue
        target_inbox = INBOX_DIR / sid
        if not target_inbox.exists():
            continue
        msg = {
            "id": str(uuid.uuid4()), "from": sender, "to": sid,
            "payload": message, "type": msg_type, "priority": priority,
            "ts": _now_iso(), "broadcast": True,
        }
        tmp = target_inbox / f"{msg['id']}.tmp"
        tmp.write_text(json.dumps(msg, indent=2))
        tmp.rename(target_inbox / f"{msg['id']}.json")
        sent += 1
    return {"status": "ok", "sent": sent}


def ls(alive_only=False):
    """List registered sessions."""
    if is_cloud():
        params = "?alive=true" if alive_only else ""
        return _api("GET", f"/sessions{params}")

    _ensure_dirs()
    registry = _load_registry()
    now = datetime.now(timezone.utc)
    sessions = []
    for sid, data in sorted(registry.items(), key=lambda x: x[1].get("alias", "")):
        hb = _parse_iso(data["heartbeat"])
        age = now - hb
        alive = _is_alive(data)
        if alive_only and not alive:
            continue
        inbox = INBOX_DIR / sid
        sessions.append({
            "id": sid, "alias": data.get("alias", "") or "-",
            "desc": data.get("desc", ""), "tool": data.get("tool", "unknown"),
            "status": "alive" if alive else "stale",
            "pending": len(list(inbox.glob("*.json"))) if inbox.exists() else 0,
            "heartbeat": data["heartbeat"],
            "heartbeat_age_sec": int(age.total_seconds()),
        })
    return sessions


def resolve(alias):
    """Resolve an alias to session data."""
    if is_cloud():
        return _api("GET", f"/resolve/{alias}")

    sid, data = _resolve_alias(alias)
    if sid:
        return data
    raise RuntimeError(f"Alias '{alias}' not found")


def get_status():
    """Get message queue status."""
    if is_cloud():
        return _api("GET", "/status")

    _ensure_dirs()
    registry = _load_registry()
    alive_count = sum(1 for d in registry.values() if _is_alive(d))
    total_pending = 0
    for sid in registry:
        inbox = INBOX_DIR / sid
        if inbox.exists():
            total_pending += len(list(inbox.glob("*.json")))
    return {
        "version": VERSION,
        "mode": "local",
        "path": str(MQ_DIR),
        "sessions": {"total": len(registry), "alive": alive_count},
        "messages": {"pending": total_pending, "delivered": len(list(DONE_DIR.glob("*.json")))},
    }


def heartbeat(session_id):
    """Update session heartbeat."""
    _sanitize_id(session_id)
    if is_cloud():
        return _api("POST", f"/heartbeat/{session_id}")

    _ensure_dirs()
    reg_file = REGISTRY_DIR / f"{session_id}.json"
    if not reg_file.exists():
        raise RuntimeError(f"{session_id[:12]}... not registered")
    data = json.loads(reg_file.read_text())
    data["heartbeat"] = _now_iso()
    reg_file.write_text(json.dumps(data, indent=2))
    return {"status": "ok"}


def history(limit=20):
    """View message history (local only)."""
    if is_cloud():
        return []

    _ensure_dirs()
    files = sorted(DONE_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:limit]
    registry = _load_registry()
    messages = []
    for f in files:
        try:
            msg = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        msg["_sender_alias"] = registry.get(msg.get("from", ""), {}).get("alias", "")
        msg["_target_alias"] = registry.get(msg.get("to", ""), {}).get("alias", "")
        messages.append(msg)
    return messages


def clean(timeout_min=10):
    """Clean stale sessions."""
    if is_cloud():
        return _api("DELETE", f"/clean?timeout={timeout_min}")

    _ensure_dirs()
    now = datetime.now(timezone.utc)
    timeout = timedelta(minutes=timeout_min)
    cleaned = 0
    for reg_file in list(REGISTRY_DIR.glob("*.json")):
        try:
            data = json.loads(reg_file.read_text())
        except json.JSONDecodeError:
            reg_file.unlink()
            continue
        hb = _parse_iso(data["heartbeat"])
        if now - hb > timeout:
            sid = data["id"]
            reg_file.unlink()
            inbox = INBOX_DIR / sid
            if inbox.exists():
                for f in inbox.glob("*"):
                    f.unlink()
                inbox.rmdir()
            cleaned += 1
    return {"status": "ok", "cleaned": cleaned}
