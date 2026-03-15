#!/usr/bin/env python3
"""agent-mq CLI — message queue for AI coding assistants."""

import argparse
import json
import sys

import core


def _print_messages(messages, as_json=False):
    if as_json:
        print(json.dumps(messages, indent=2, ensure_ascii=False))
        return
    for msg in messages:
        mt = msg.get("type", "text")
        pri = "!" if msg.get("priority") == "urgent" else ""
        print(f"[{msg['ts']}] {pri}{mt} from={msg['from']} msg={msg['id'][:8]}...")
        if msg.get("reply_to"):
            print(f"  reply_to: {msg['reply_to'][:8]}...")
        print(f"  {msg['payload']}\n")


def cmd_add(args):
    try:
        result = core.add(args.name, args.desc or "", args.tool or "claude-code")
        print(f"added {result['name']}")
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr); sys.exit(1)


def cmd_send(args):
    try:
        result = core.send(args.target, args.message, args.sender,
                           args.type or "text", args.priority or "normal", args.reply_to)
        print(f"sent {result['id'][:8]}... -> {result['to']}")
    except (RuntimeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr); sys.exit(1)


def cmd_recv(args):
    try:
        messages = core.recv(args.name, args.peek, args.type)
        _print_messages(messages, args.json)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr); sys.exit(1)


def cmd_ls(args):
    try:
        agents = core.ls()
        if args.json:
            print(json.dumps(agents, indent=2, ensure_ascii=False))
            return
        if not agents:
            print("no registered agents."); return
        for a in agents:
            line = f"  {a['name']}  tool={a.get('tool', '?')}  inbox={a.get('pending', 0)}"
            if a.get("desc"):
                line += f"  desc={a['desc']}"
            print(line)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr); sys.exit(1)


def cmd_history(args):
    try:
        messages = core.history(args.limit or 20)
        if not messages:
            print("no message history."); return
        if args.json:
            print(json.dumps(messages, indent=2, ensure_ascii=False))
            return
        for msg in messages:
            print(f"[{msg.get('ts', '?')}] {msg.get('type', 'text')} {msg['from']} -> {msg['to']}: {msg.get('payload', '')[:80]}")
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr); sys.exit(1)


def cmd_register(args):
    try:
        result = core.register(args.server)
        print(f"registered. token: {result['token']}")
        print(f"save this token — you'll need it to login again.")
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr); sys.exit(1)


def cmd_login(args):
    core.save_config({"mode": "cloud", "server": args.server.rstrip("/"), "token": args.token})
    print(f"logged in to {args.server}")


def cmd_logout(_args):
    core.save_config({"mode": "local", "server": "", "token": ""})
    print("logged out. switched to local mode.")


def main():
    parser = argparse.ArgumentParser(
        prog="mq",
        description=f"agent-mq v{core.VERSION} — Message queue for AI coding assistants",
    )
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("add", help="Add an agent")
    p.add_argument("name"); p.add_argument("--desc", default="")
    p.add_argument("--tool", default="claude-code")

    p = sub.add_parser("send", help="Send a message")
    p.add_argument("target"); p.add_argument("message")
    p.add_argument("--from", dest="sender", required=True)
    p.add_argument("--reply-to"); p.add_argument("--type", choices=core.MSG_TYPES, default="text")
    p.add_argument("--priority", choices=core.PRIORITIES, default="normal")

    p = sub.add_parser("recv", help="Receive messages")
    p.add_argument("name"); p.add_argument("--peek", action="store_true")
    p.add_argument("--json", action="store_true"); p.add_argument("--type", choices=core.MSG_TYPES)

    p = sub.add_parser("ls", help="List agents")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("history", help="View message history")
    p.add_argument("--limit", type=int, default=20); p.add_argument("--json", action="store_true")

    p = sub.add_parser("register", help="Register account on cloud server")
    p.add_argument("--server", required=True)

    p = sub.add_parser("login", help="Login to cloud server")
    p.add_argument("--server", required=True); p.add_argument("--token", required=True)

    sub.add_parser("logout", help="Switch to local mode")

    args = parser.parse_args()
    dispatch = {
        "add": cmd_add, "send": cmd_send, "recv": cmd_recv,
        "ls": cmd_ls, "history": cmd_history,
        "register": cmd_register, "login": cmd_login, "logout": cmd_logout,
    }
    if args.cmd in dispatch:
        dispatch[args.cmd](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
