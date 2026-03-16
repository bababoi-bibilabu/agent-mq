"""agent-mq core — shared logic for MCP server and CLI.

Returns structured data (dict/list). Raises on errors.
Handles both local (file-based) and cloud (HTTP relay) modes.
"""

import json
import os
import uuid
from datetime import datetime, timezone
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
        raise RuntimeError("Server URL not configured. Run `mq register` first.")

    url = f"{server}/api/v1{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json", "User-Agent": f"agent-mq/{VERSION}"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=10) as resp:
            raw = resp.read().decode()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                raise RuntimeError(f"Server returned invalid JSON: {raw[:200]}")
    except HTTPError as e:
        detail = e.reason
        try:
            if e.headers.get("content-type", "").startswith("application/json"):
                detail = json.loads(e.read().decode()).get("detail", e.reason)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            pass
        raise RuntimeError(detail)
    except URLError as e:
        raise RuntimeError(f"Cannot reach server: {e.reason}")
    except (TimeoutError, ConnectionError, OSError) as e:
        raise RuntimeError(f"Network error: {e}")


# ── Local helpers ──

def _ensure_dirs():
    for d in [REGISTRY_DIR, INBOX_DIR, DONE_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sanitize_name(name):
    """Reject path traversal in agent names."""
    if "/" in name or "\\" in name or ".." in name or "\0" in name:
        raise ValueError(f"Invalid agent name: {name!r}")
    return name


def _load_registry():
    _ensure_dirs()
    result = {}
    for f in REGISTRY_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            result[data["name"]] = data
        except (json.JSONDecodeError, KeyError):
            pass
    return result


def _write_msg(inbox_dir, msg):
    """Atomically write a message to an inbox directory."""
    tmp = inbox_dir / f"{msg['id']}.tmp"
    tmp.write_text(json.dumps(msg, indent=2))
    tmp.rename(inbox_dir / f"{msg['id']}.json")


# ── Core operations ──

def add(name, desc="", tool="claude-code"):
    """Add an agent to the message queue."""
    _sanitize_name(name)
    if is_cloud():
        return _api("POST", "/agents", {"name": name, "desc": desc, "tool": tool})

    _ensure_dirs()
    (INBOX_DIR / name).mkdir(exist_ok=True)
    data = {
        "name": name, "desc": desc,
        "tool": tool, "registered_at": _now_iso(), "version": VERSION,
    }
    (REGISTRY_DIR / f"{name}.json").write_text(json.dumps(data, indent=2))
    return {"status": "ok", "name": name}


def send(target, message, sender, msg_type="text", priority="normal", reply_to=None):
    """Send a message to a target agent by name."""
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
    _sanitize_name(target)

    target_inbox = INBOX_DIR / target
    if not target_inbox.exists():
        raise RuntimeError(f"Target '{target}' not found")

    msg = {
        "id": str(uuid.uuid4()), "from": sender, "to": target,
        "payload": message, "type": msg_type, "priority": priority, "ts": _now_iso(),
    }
    if reply_to:
        msg["reply_to"] = reply_to

    _write_msg(target_inbox, msg)
    return {"status": "ok", "id": msg["id"], "to": target}


def recv(name, peek=False, msg_type=None):
    """Receive messages from an agent's inbox."""
    _sanitize_name(name)
    if is_cloud():
        params = f"?peek={'true' if peek else 'false'}"
        if msg_type:
            params += f"&type={msg_type}"
        return _api("GET", f"/recv/{name}{params}")

    _ensure_dirs()
    inbox = INBOX_DIR / name
    if not inbox.exists():
        return []

    files = sorted(inbox.glob("*.json"), key=lambda f: f.stat().st_mtime)
    if not files:
        return []

    messages = []
    for f in files:
        try:
            msg = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        if msg_type and msg.get("type", "text") != msg_type:
            continue
        messages.append(msg)
        if not peek:
            f.rename(DONE_DIR / f.name)

    return messages


def ls():
    """List registered agents."""
    if is_cloud():
        return _api("GET", "/agents")

    _ensure_dirs()
    registry = _load_registry()
    agents = []
    for name, data in sorted(registry.items()):
        inbox = INBOX_DIR / name
        agents.append({
            "name": name,
            "desc": data.get("desc", ""),
            "tool": data.get("tool", "unknown"),
            "pending": sum(1 for _ in inbox.glob("*.json")) if inbox.exists() else 0,
        })
    return agents


def history(limit=20):
    """View message history."""
    if is_cloud():
        return _api("GET", f"/history?limit={limit}")

    _ensure_dirs()
    files = sorted(DONE_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:limit]
    messages = []
    for f in files:
        try:
            msg = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        messages.append(msg)
    return messages
