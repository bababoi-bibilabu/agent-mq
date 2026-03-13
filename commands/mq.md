---
name: mq
description: "Manage inter-session message queue: send, receive, list sessions, broadcast"
argument-hint: "<send|recv|ls|broadcast|status> [args...]"
allowed-tools: Bash, Read
---

Run the `mq` command with the provided arguments.

If no arguments given, run `mq status` to show a quick overview.

```bash
mq $ARGUMENTS
```

If the user wants to register this session, auto-detect the session ID:

```bash
mq auto-register --alias "$ARGUMENTS"
```

If the user wants to set up polling, use CronCreate with a 5-minute interval to poll the inbox and process messages.
