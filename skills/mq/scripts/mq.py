#!/usr/bin/env python3
"""agent-mq CLI — thin wrapper around core for non-MCP platforms.

For MCP-capable platforms (Claude Code, Codex, OpenClaw), use mcp_server.py instead.
"""

import argparse
import json
import sys
from pathlib import Path

import core


def _print_messages(messages, as_json=False):
    if as_json:
        print(json.dumps(messages, indent=2, ensure_ascii=False))
        return
    for msg in messages:
        alias = msg.get("_sender_alias", "")
        label = f"{alias} ({msg['from'][:8]}...)" if alias else msg["from"][:12] + "..."
        mt = msg.get("type", "text")
        pri = "!" if msg.get("priority") == "urgent" else ""
        print(f"[{msg['ts']}] {pri}{mt} from={label} msg={msg['id'][:8]}...")
        if msg.get("reply_to"):
            print(f"  reply_to: {msg['reply_to'][:8]}...")
        print(f"  {msg['payload']}\n")


def cmd_register(args):
    try:
        result = core.register(args.id, args.alias or "", args.desc or "", args.tool or "claude-code")
        mode = " [cloud]" if core.is_cloud() else ""
        print(f"registered {args.id[:12]}... alias={result.get('alias', '')}{mode}")
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr); sys.exit(1)


def cmd_send(args):
    try:
        result = core.send(
            args.target, args.message, args.sender,
            getattr(args, "type", "text") or "text",
            getattr(args, "priority", "normal") or "normal",
            args.reply_to,
        )
        mt = getattr(args, "type", "text") or "text"
        pri = getattr(args, "priority", "normal") or "normal"
        mode = " [cloud]" if core.is_cloud() else ""
        label = result.get("label", result.get("to", "")[:12] + "...")
        print(f"sent {result['id'][:8]}... -> {label} [{mt}:{pri}]{mode}")
    except (RuntimeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr); sys.exit(1)


def cmd_recv(args):
    try:
        messages = core.recv(
            args.id,
            getattr(args, "peek", False),
            getattr(args, "type", None),
        )
        _print_messages(messages, getattr(args, "json", False))
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr); sys.exit(1)


def cmd_broadcast(args):
    try:
        result = core.broadcast(
            args.message, args.sender,
            getattr(args, "type", "text") or "text",
            getattr(args, "priority", "normal") or "normal",
        )
        mt = getattr(args, "type", "text") or "text"
        pri = getattr(args, "priority", "normal") or "normal"
        mode = " [cloud]" if core.is_cloud() else ""
        print(f"broadcast to {result['sent']} session(s) [{mt}:{pri}]{mode}")
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr); sys.exit(1)


def cmd_ls(args):
    try:
        sessions = core.ls(getattr(args, "alive", False))
        if getattr(args, "json", False):
            print(json.dumps(sessions, indent=2, ensure_ascii=False))
            return
        if not sessions:
            print("no registered sessions."); return
        for s in sessions:
            print(f"  {s['id']}")
            print(f"    alias: {s.get('alias', '-')}  status: {s['status']}  tool: {s.get('tool', '?')}  inbox: {s.get('pending', 0)}")
            if s.get("desc"):
                print(f"    desc: {s['desc']}")
            hb = s.get("heartbeat", "?")
            age = s.get("heartbeat_age_sec")
            hb_str = f"{hb} ({age}s ago)" if age is not None else hb
            print(f"    heartbeat: {hb_str}\n")
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr); sys.exit(1)


def cmd_resolve(args):
    try:
        data = core.resolve(args.alias)
        if getattr(args, "json", False):
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(data["id"])
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr); sys.exit(1)


def cmd_status(_args):
    try:
        s = core.get_status()
        if core.is_cloud():
            print(f"agent-mq v{s['version']}")
            print(f"  mode: cloud ({core.load_config()['server']})")
        else:
            print(f"agent-mq v{s['version']}")
            print(f"  mode: local ({s.get('path', core.MQ_DIR)})")
        sess = s["sessions"]
        stale = sess["total"] - sess["alive"]
        print(f"  sessions: {sess['alive']} alive, {stale} stale")
        msgs = s["messages"]
        print(f"  messages: {msgs['pending']} pending, {msgs['delivered']} delivered")
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr); sys.exit(1)


def cmd_heartbeat(args):
    try:
        core.heartbeat(args.id)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr); sys.exit(1)


def cmd_history(args):
    try:
        messages = core.history(getattr(args, "limit", 20) or 20)
        if not messages:
            print("no message history."); return
        if getattr(args, "json", False):
            print(json.dumps(messages, indent=2, ensure_ascii=False))
            return
        registry = {}
        for msg in messages:
            sl = msg.get("_sender_alias") or msg.get("from", "?")[:12] + "..."
            tl = msg.get("_target_alias") or msg.get("to", "?")[:12] + "..."
            print(f"[{msg.get('ts', '?')}] {msg.get('type', 'text')} {sl} -> {tl}: {msg.get('payload', '')[:80]}")
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr); sys.exit(1)


def cmd_clean(args):
    try:
        result = core.clean(args.timeout)
        mode = " [cloud]" if core.is_cloud() else ""
        print(f"cleaned {result['cleaned']} stale sessions{mode}")
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr); sys.exit(1)


def cmd_auto_register(args):
    core._ensure_dirs()
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
    try:
        core.register(session_id, args.alias or cwd.name, args.desc or f"Session in {cwd}", args.tool or "claude-code")
        print(f"SESSION_ID={session_id}")
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr); sys.exit(1)


def cmd_login(args):
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    server = args.server
    token = args.token or ""

    if not server:
        try:
            server = input("Server URL: ").strip().rstrip("/")
            if not server:
                print("error: server URL required", file=sys.stderr); sys.exit(1)
            token = input("Token (optional, press Enter to skip): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\ncancelled."); sys.exit(0)

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

    core.save_config({"mode": "cloud", "server": server, "token": token})
    print(f"logged in. config saved to {core.CONFIG_FILE}")
    print(f"all mq commands now use cloud mode.")


def cmd_logout(_args):
    core.save_config({"mode": "local", "server": "", "token": ""})
    print("logged out. switched to local mode.")


def cmd_config(_args):
    cfg = core.load_config()
    print(f"config: {core.CONFIG_FILE}")
    print(f"  mode:   {cfg['mode']}")
    print(f"  server: {cfg['server'] or '(none)'}")
    print(f"  token:  {'***' + cfg['token'][-4:] if len(cfg.get('token', '')) > 4 else '(none)'}")
    print(f"  data:   {core.MQ_DIR}")


def cmd_version(_args):
    print(f"{core.VERSION}")
    print(f"  mode: {'cloud (' + core.load_config()['server'] + ')' if core.is_cloud() else 'local'}")
    print(f"  config: {core.CONFIG_FILE}")


def main():
    parser = argparse.ArgumentParser(
        prog="mq",
        description=f"agent-mq v{core.VERSION} — Message queue for AI coding assistants",
    )
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("register")
    p.add_argument("id"); p.add_argument("--alias"); p.add_argument("--desc")
    p.add_argument("--tool", default="claude-code")

    p = sub.add_parser("send")
    p.add_argument("target"); p.add_argument("message")
    p.add_argument("--from", dest="sender", required=True)
    p.add_argument("--reply-to"); p.add_argument("--type", choices=core.MSG_TYPES, default="text")
    p.add_argument("--priority", choices=core.PRIORITIES, default="normal")

    p = sub.add_parser("recv")
    p.add_argument("id"); p.add_argument("--peek", action="store_true")
    p.add_argument("--json", action="store_true"); p.add_argument("--type", choices=core.MSG_TYPES)

    p = sub.add_parser("broadcast")
    p.add_argument("message"); p.add_argument("--from", dest="sender", required=True)
    p.add_argument("--type", choices=core.MSG_TYPES, default="text")
    p.add_argument("--priority", choices=core.PRIORITIES, default="normal")

    p = sub.add_parser("ls")
    p.add_argument("--json", action="store_true"); p.add_argument("--alive", action="store_true")

    p = sub.add_parser("resolve")
    p.add_argument("alias"); p.add_argument("--json", action="store_true")

    sub.add_parser("status")

    p = sub.add_parser("heartbeat"); p.add_argument("id")

    p = sub.add_parser("history")
    p.add_argument("--limit", type=int, default=20); p.add_argument("--json", action="store_true")

    p = sub.add_parser("clean")
    p.add_argument("--timeout", type=int, default=core.HEARTBEAT_TIMEOUT_MIN)

    p = sub.add_parser("auto-register")
    p.add_argument("--alias"); p.add_argument("--desc")
    p.add_argument("--tool", default="claude-code")

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
