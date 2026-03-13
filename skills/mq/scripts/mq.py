#!/usr/bin/env python3
"""agent-mq: Message queue for AI coding assistants.

Two modes:
  local  — file-based (default, zero dependencies)
  cloud  — HTTP relay server (after `mq login`)

Config: ~/.agent-mq/config.json (managed via `mq login` / `mq logout`)
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

VERSION = "0.1.0"
PRODUCT = "agent-mq"

# ── Config ──

CONFIG_DIR = Path.home() / ".agent-mq"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config():
    """Load config. No login = local mode."""
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


CFG = load_config()
MODE = CFG["mode"]
SERVER_URL = CFG["server"]
AUTH_TOKEN = CFG["token"]

MQ_DIR = Path.home() / ".claude" / "mq"
REGISTRY_DIR = MQ_DIR / "registry"
INBOX_DIR = MQ_DIR / "inbox"
DONE_DIR = MQ_DIR / "done"
HEARTBEAT_TIMEOUT_MIN = 10

MSG_TYPES = ("text", "task", "query", "response", "status")
PRIORITIES = ("low", "normal", "urgent")


def is_cloud():
    return MODE == "cloud"


# ══════════════════════════════════════════
#  Cloud transport (urllib, zero dependencies)
# ══════════════════════════════════════════

def _api(method, path, body=None):
    """Make an API call to the cloud server."""
    if not SERVER_URL:
        print("error: AGENT_MQ_SERVER not set", file=sys.stderr)
        sys.exit(1)

    url = f"{SERVER_URL}/api/v1{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"

    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        err = json.loads(e.read().decode()) if e.headers.get("content-type", "").startswith("application/json") else {}
        detail = err.get("detail", e.reason)
        print(f"error: {detail}", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"error: cannot reach server: {e.reason}", file=sys.stderr)
        sys.exit(1)


# ══════════════════════════════════════════
#  Local helpers
# ══════════════════════════════════════════

def ensure_dirs():
    for d in [REGISTRY_DIR, INBOX_DIR, DONE_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    s = s.rstrip("Z")
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def load_registry():
    ensure_dirs()
    result = {}
    for f in REGISTRY_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            result[data["id"]] = data
        except (json.JSONDecodeError, KeyError):
            pass
    return result


def resolve_alias_local(alias):
    registry = load_registry()
    for sid, data in registry.items():
        if data.get("alias", "").lower() == alias.lower():
            return sid, data
    return None, None


def resolve_target_local(target):
    if len(target) > 20 and "-" in target:
        return target
    sid, _ = resolve_alias_local(target)
    if sid:
        return sid
    return target


def is_alive(data):
    try:
        hb = parse_iso(data["heartbeat"])
        age = datetime.now(timezone.utc) - hb
        return age < timedelta(minutes=HEARTBEAT_TIMEOUT_MIN)
    except (KeyError, ValueError):
        return False


# ══════════════════════════════════════════
#  Commands — each handles both local & cloud
# ══════════════════════════════════════════

def cmd_register(args):
    if is_cloud():
        result = _api("POST", "/register", {
            "id": args.id, "alias": args.alias or "", "desc": args.desc or "", "tool": args.tool or "claude-code",
        })
        print(f"registered {args.id[:12]}... alias={result.get('alias', '')} [cloud]")
        return

    ensure_dirs()
    sid = args.id
    (INBOX_DIR / sid).mkdir(exist_ok=True)
    reg_file = REGISTRY_DIR / f"{sid}.json"
    data = {
        "id": sid, "alias": args.alias or "", "desc": args.desc or "",
        "tool": args.tool or "claude-code", "heartbeat": now_iso(),
        "registered_at": now_iso(), "version": VERSION,
    }
    reg_file.write_text(json.dumps(data, indent=2))
    print(f"registered {sid[:12]}... alias={data['alias']} tool={data['tool']}")


def cmd_send(args):
    msg_type = getattr(args, "type", "text") or "text"
    priority = getattr(args, "priority", "normal") or "normal"

    if msg_type not in MSG_TYPES:
        print(f"error: invalid type '{msg_type}'", file=sys.stderr); sys.exit(1)
    if priority not in PRIORITIES:
        print(f"error: invalid priority '{priority}'", file=sys.stderr); sys.exit(1)

    if is_cloud():
        body = {
            "target": args.target, "message": args.message, "from": args.sender,
            "type": msg_type, "priority": priority,
        }
        if args.reply_to:
            body["reply_to"] = args.reply_to
        result = _api("POST", "/send", body)
        print(f"sent {result['id'][:8]}... -> {result['to'][:12]}... [{msg_type}:{priority}] [cloud]")
        return

    ensure_dirs()
    target = resolve_target_local(args.target)
    target_inbox = INBOX_DIR / target
    if not target_inbox.exists():
        print(f"error: target '{args.target}' not found", file=sys.stderr); sys.exit(1)

    msg = {
        "id": str(uuid.uuid4()), "from": args.sender, "to": target,
        "payload": args.message, "type": msg_type, "priority": priority, "ts": now_iso(),
    }
    if args.reply_to:
        msg["reply_to"] = args.reply_to

    msg_file = target_inbox / f"{msg['id']}.json"
    tmp_file = target_inbox / f"{msg['id']}.tmp"
    tmp_file.write_text(json.dumps(msg, indent=2))
    tmp_file.rename(msg_file)

    registry = load_registry()
    label = registry.get(target, {}).get("alias", "") or target[:12] + "..."
    print(f"sent {msg['id'][:8]}... -> {label} [{msg_type}:{priority}]")


def cmd_recv(args):
    if is_cloud():
        params = f"?peek={'true' if getattr(args, 'peek', False) else 'false'}"
        filter_type = getattr(args, "type", None)
        if filter_type:
            params += f"&type={filter_type}"
        messages = _api("GET", f"/recv/{args.id}{params}")
        if getattr(args, "json", False):
            print(json.dumps(messages, indent=2, ensure_ascii=False))
        else:
            for msg in messages:
                alias = msg.get("_sender_alias", "")
                label = f"{alias} ({msg['from'][:8]}...)" if alias else msg["from"][:12] + "..."
                mt = msg.get("type", "text")
                pri = "!" if msg.get("priority") == "urgent" else ""
                print(f"[{msg['ts']}] {pri}{mt} from={label} msg={msg['id'][:8]}...")
                if msg.get("reply_to"):
                    print(f"  reply_to: {msg['reply_to'][:8]}...")
                print(f"  {msg['payload']}\n")
        return

    ensure_dirs()
    inbox = INBOX_DIR / args.id
    if not inbox.exists():
        if getattr(args, "json", False): print("[]")
        return

    files = sorted(inbox.glob("*.json"))
    if not files:
        if getattr(args, "json", False): print("[]")
        return

    registry = load_registry()
    messages = []
    filter_type = getattr(args, "type", None)

    for f in files:
        try:
            msg = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        if filter_type and msg.get("type", "text") != filter_type:
            continue

        sender_alias = registry.get(msg.get("from", ""), {}).get("alias", "")

        if getattr(args, "json", False):
            msg["_sender_alias"] = sender_alias
            messages.append(msg)
        else:
            label = f"{sender_alias} ({msg['from'][:8]}...)" if sender_alias else msg["from"][:12] + "..."
            mt = msg.get("type", "text")
            pri = "!" if msg.get("priority") == "urgent" else ""
            print(f"[{msg['ts']}] {pri}{mt} from={label} msg={msg['id'][:8]}...")
            if msg.get("reply_to"):
                print(f"  reply_to: {msg['reply_to'][:8]}...")
            print(f"  {msg['payload']}\n")

        if not getattr(args, "peek", False):
            (DONE_DIR / f.name).parent.mkdir(parents=True, exist_ok=True)
            f.rename(DONE_DIR / f.name)

    if getattr(args, "json", False):
        print(json.dumps(messages, indent=2, ensure_ascii=False))


def cmd_broadcast(args):
    msg_type = getattr(args, "type", "text") or "text"
    priority = getattr(args, "priority", "normal") or "normal"

    if is_cloud():
        result = _api("POST", "/broadcast", {
            "message": args.message, "from": args.sender,
            "type": msg_type, "priority": priority,
        })
        print(f"broadcast to {result['sent']} session(s) [{msg_type}:{priority}] [cloud]")
        return

    ensure_dirs()
    registry = load_registry()
    sent = 0
    for sid, data in registry.items():
        if sid == args.sender or not is_alive(data):
            continue
        target_inbox = INBOX_DIR / sid
        if not target_inbox.exists():
            continue
        msg = {
            "id": str(uuid.uuid4()), "from": args.sender, "to": sid,
            "payload": args.message, "type": msg_type, "priority": priority,
            "ts": now_iso(), "broadcast": True,
        }
        tmp = target_inbox / f"{msg['id']}.tmp"
        tmp.write_text(json.dumps(msg, indent=2))
        tmp.rename(target_inbox / f"{msg['id']}.json")
        sent += 1
    print(f"broadcast to {sent} alive session(s) [{msg_type}:{priority}]")


def cmd_ls(args):
    if is_cloud():
        params = "?alive=true" if getattr(args, "alive", False) else ""
        sessions = _api("GET", f"/sessions{params}")
        if getattr(args, "json", False):
            print(json.dumps(sessions, indent=2, ensure_ascii=False))
        else:
            if not sessions:
                print("no registered sessions."); return
            for s in sessions:
                print(f"  {s['id']}")
                print(f"    alias: {s.get('alias', '-')}  status: {s['status']}  tool: {s.get('tool', '?')}  inbox: {s.get('pending', 0)}")
                if s.get("desc"):
                    print(f"    desc: {s['desc']}")
                print(f"    heartbeat: {s.get('heartbeat', '?')}\n")
        return

    ensure_dirs()
    registry = load_registry()
    if not registry:
        print("no registered sessions."); return

    now = datetime.now(timezone.utc)
    sessions = []
    for sid, data in sorted(registry.items(), key=lambda x: x[1].get("alias", "")):
        hb = parse_iso(data["heartbeat"])
        age = now - hb
        age_sec = int(age.total_seconds())
        alive = is_alive(data)
        if getattr(args, "alive", False) and not alive:
            continue
        alias = data.get("alias", "") or "-"
        desc = data.get("desc", "")
        tool = data.get("tool", "unknown")
        inbox = INBOX_DIR / sid
        pending = len(list(inbox.glob("*.json"))) if inbox.exists() else 0
        status = "alive" if alive else "STALE"
        if getattr(args, "json", False):
            sessions.append({"id": sid, "alias": alias, "desc": desc, "tool": tool,
                             "status": status, "pending": pending, "heartbeat": data["heartbeat"],
                             "heartbeat_age_sec": age_sec})
        else:
            print(f"  {sid}")
            print(f"    alias: {alias}  status: {status}  tool: {tool}  inbox: {pending}")
            if desc: print(f"    desc: {desc}")
            print(f"    heartbeat: {data['heartbeat']} ({age_sec}s ago)\n")
    if getattr(args, "json", False):
        print(json.dumps(sessions, indent=2, ensure_ascii=False))


def cmd_resolve(args):
    if is_cloud():
        data = _api("GET", f"/resolve/{args.alias}")
        if getattr(args, "json", False):
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(data["id"])
        return

    sid, data = resolve_alias_local(args.alias)
    if sid:
        if getattr(args, "json", False):
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(sid)
    else:
        print(f"error: alias '{args.alias}' not found", file=sys.stderr); sys.exit(1)


def cmd_status(_args):
    if is_cloud():
        s = _api("GET", "/status")
        mode_label = f"cloud ({SERVER_URL})"
        print(f"agent-mq v{s['version']}")
        print(f"  mode: {mode_label}")
        print(f"  sessions: {s['sessions']['alive']} alive, {s['sessions']['total'] - s['sessions']['alive']} stale")
        print(f"  messages: {s['messages']['pending']} pending, {s['messages']['delivered']} delivered")
        return

    ensure_dirs()
    registry = load_registry()
    alive_count = sum(1 for d in registry.values() if is_alive(d))
    stale_count = len(registry) - alive_count
    total_pending = 0
    total_done = len(list(DONE_DIR.glob("*.json")))
    for sid in registry:
        inbox = INBOX_DIR / sid
        if inbox.exists():
            total_pending += len(list(inbox.glob("*.json")))
    print(f"agent-mq v{VERSION}")
    print(f"  mode: local ({MQ_DIR})")
    print(f"  sessions: {alive_count} alive, {stale_count} stale")
    print(f"  messages: {total_pending} pending, {total_done} delivered")


def cmd_heartbeat(args):
    if is_cloud():
        _api("POST", f"/heartbeat/{args.id}")
        return

    ensure_dirs()
    reg_file = REGISTRY_DIR / f"{args.id}.json"
    if not reg_file.exists():
        print(f"error: {args.id[:12]}... not registered", file=sys.stderr); sys.exit(1)
    data = json.loads(reg_file.read_text())
    data["heartbeat"] = now_iso()
    reg_file.write_text(json.dumps(data, indent=2))


def cmd_history(args):
    if is_cloud():
        print("history not available in cloud mode (messages not stored long-term)")
        return

    ensure_dirs()
    files = sorted(DONE_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    limit = getattr(args, "limit", 20) or 20
    files = files[:limit]
    if not files:
        print("no message history."); return

    registry = load_registry()
    messages = []
    for f in files:
        try:
            msg = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        sa = registry.get(msg.get("from", ""), {}).get("alias", "")
        ta = registry.get(msg.get("to", ""), {}).get("alias", "")
        if getattr(args, "json", False):
            msg["_sender_alias"] = sa; msg["_target_alias"] = ta
            messages.append(msg)
        else:
            sl = sa or msg.get("from", "?")[:12] + "..."
            tl = ta or msg.get("to", "?")[:12] + "..."
            print(f"[{msg.get('ts', '?')}] {msg.get('type', 'text')} {sl} -> {tl}: {msg.get('payload', '')[:80]}")
    if getattr(args, "json", False):
        print(json.dumps(messages, indent=2, ensure_ascii=False))


def cmd_clean(args):
    if is_cloud():
        result = _api("DELETE", f"/clean?timeout={args.timeout}")
        print(f"cleaned {result['cleaned']} stale sessions [cloud]")
        return

    ensure_dirs()
    now = datetime.now(timezone.utc)
    timeout = timedelta(minutes=args.timeout)
    cleaned = 0
    for reg_file in list(REGISTRY_DIR.glob("*.json")):
        try:
            data = json.loads(reg_file.read_text())
        except json.JSONDecodeError:
            reg_file.unlink(); continue
        hb = parse_iso(data["heartbeat"])
        if now - hb > timeout:
            sid = data["id"]
            alias = data.get("alias", "")
            reg_file.unlink()
            inbox = INBOX_DIR / sid
            if inbox.exists():
                for f in inbox.glob("*"): f.unlink()
                inbox.rmdir()
            print(f"cleaned {sid[:12]}... ({alias})")
            cleaned += 1
    print(f"total: {cleaned} stale sessions removed.")


def cmd_auto_register(args):
    ensure_dirs()
    cwd = Path.cwd()
    project_hash = str(cwd).replace("/", "-")
    projects_dir = Path.home() / ".claude" / "projects" / project_hash

    if not projects_dir.exists():
        base = Path.home() / ".claude" / "projects"
        if base.exists():
            candidates = [d for d in base.iterdir() if d.is_dir() and d.name.endswith(cwd.name)]
            if candidates:
                projects_dir = candidates[0]
            else:
                print("error: cannot detect session ID", file=sys.stderr); sys.exit(1)
        else:
            print("error: ~/.claude/projects/ not found", file=sys.stderr); sys.exit(1)

    jsonl_files = sorted(projects_dir.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not jsonl_files:
        print("error: no transcript files found", file=sys.stderr); sys.exit(1)

    session_id = jsonl_files[0].stem

    class A: pass
    a = A()
    a.id = session_id
    a.alias = args.alias or cwd.name
    a.desc = args.desc or f"Session in {cwd}"
    a.tool = args.tool or "claude-code"
    cmd_register(a)
    print(f"SESSION_ID={session_id}")


def cmd_version(_args):
    print(f"{PRODUCT} v{VERSION}")
    print(f"  mode: {'cloud (' + SERVER_URL + ')' if is_cloud() else 'local'}")
    print(f"  config: {CONFIG_FILE}")


# ── login / logout / config ──

def cmd_login(args):
    server = args.server
    token = args.token or ""

    if not server:
        # Interactive prompt
        try:
            server = input("Server URL: ").strip().rstrip("/")
            if not server:
                print("error: server URL required", file=sys.stderr); sys.exit(1)
            token = input("Token (optional, press Enter to skip): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\ncancelled."); sys.exit(0)

    # Verify server is reachable
    url = f"{server}/api/v1/status"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers, method="GET")
    try:
        with urlopen(req, timeout=10) as resp:
            info = json.loads(resp.read().decode())
            print(f"connected to {server} (v{info.get('version', '?')})")
    except (HTTPError, URLError) as e:
        reason = getattr(e, "reason", str(e))
        print(f"warning: cannot reach server ({reason}), saving config anyway")

    cfg = {"mode": "cloud", "server": server, "token": token}
    save_config(cfg)
    print(f"logged in. config saved to {CONFIG_FILE}")
    print(f"all mq commands now use cloud mode.")


def cmd_logout(_args):
    cfg = {"mode": "local", "server": "", "token": ""}
    save_config(cfg)
    print(f"logged out. switched to local mode.")


def cmd_config(_args):
    cfg = load_config()
    print(f"config: {CONFIG_FILE}")
    print(f"  mode:   {cfg['mode']}")
    print(f"  server: {cfg['server'] or '(none)'}")
    print(f"  token:  {'***' + cfg['token'][-4:] if len(cfg.get('token', '')) > 4 else '(none)'}")
    print(f"  data:   {MQ_DIR}")


# ── main ──

def main():
    parser = argparse.ArgumentParser(
        prog="mq",
        description=f"{PRODUCT} v{VERSION} — Message queue for AI coding assistants",
    )
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("register")
    p.add_argument("id"); p.add_argument("--alias"); p.add_argument("--desc")
    p.add_argument("--tool", default="claude-code")

    p = sub.add_parser("send")
    p.add_argument("target"); p.add_argument("message")
    p.add_argument("--from", dest="sender", required=True)
    p.add_argument("--reply-to"); p.add_argument("--type", choices=MSG_TYPES, default="text")
    p.add_argument("--priority", choices=PRIORITIES, default="normal")

    p = sub.add_parser("recv")
    p.add_argument("id"); p.add_argument("--peek", action="store_true")
    p.add_argument("--json", action="store_true"); p.add_argument("--type", choices=MSG_TYPES)

    p = sub.add_parser("broadcast")
    p.add_argument("message"); p.add_argument("--from", dest="sender", required=True)
    p.add_argument("--type", choices=MSG_TYPES, default="text")
    p.add_argument("--priority", choices=PRIORITIES, default="normal")

    p = sub.add_parser("ls")
    p.add_argument("--json", action="store_true"); p.add_argument("--alive", action="store_true")

    p = sub.add_parser("resolve")
    p.add_argument("alias"); p.add_argument("--json", action="store_true")

    sub.add_parser("status")

    p = sub.add_parser("heartbeat"); p.add_argument("id")

    p = sub.add_parser("history")
    p.add_argument("--limit", type=int, default=20); p.add_argument("--json", action="store_true")

    p = sub.add_parser("clean")
    p.add_argument("--timeout", type=int, default=HEARTBEAT_TIMEOUT_MIN)

    p = sub.add_parser("auto-register")
    p.add_argument("--alias"); p.add_argument("--desc")
    p.add_argument("--tool", default="claude-code")

    # login / logout / config
    p = sub.add_parser("login", help="Connect to cloud server")
    p.add_argument("--server", help="Server URL")
    p.add_argument("--token", help="Auth token")

    sub.add_parser("logout", help="Disconnect and switch to local mode")
    sub.add_parser("config", help="Show current configuration")
    sub.add_parser("version")

    args = parser.parse_args()
    dispatch = {
        "register": cmd_register, "send": cmd_send, "recv": cmd_recv,
        "broadcast": cmd_broadcast, "ls": cmd_ls, "resolve": cmd_resolve,
        "status": cmd_status, "heartbeat": cmd_heartbeat, "history": cmd_history,
        "clean": cmd_clean, "auto-register": cmd_auto_register, "version": cmd_version,
        "login": cmd_login, "logout": cmd_logout, "config": cmd_config,
    }
    if args.cmd in dispatch:
        dispatch[args.cmd](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
