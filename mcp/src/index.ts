#!/usr/bin/env node
/**
 * agent-mq MCP server — message queue tools for AI coding assistants.
 *
 * Usage: npx agent-mq
 * Or in MCP config: {"command": "npx", "args": ["-y", "agent-mq"]}
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import * as client from "./client.js";

const server = new McpServer({ name: "agent-mq", version: "0.1.8" });

server.tool("mq_add", "Add an agent to the message queue", {
  name: z.string(),
  desc: z.string().default(""),
  tool: z.string().default("claude-code"),
}, async ({ name, desc, tool }) => ({
  content: [{ type: "text", text: JSON.stringify(await client.add(name, desc, tool)) }],
}));

server.tool("mq_send", "Send a message to a target agent by name", {
  target: z.string(),
  message: z.string(),
  sender: z.string(),
  msg_type: z.string().default("text"),
  priority: z.string().default("normal"),
  reply_to: z.string().optional(),
}, async ({ target, message, sender, msg_type, priority, reply_to }) => ({
  content: [{ type: "text", text: JSON.stringify(await client.send(target, message, sender, msg_type, priority, reply_to)) }],
}));

server.tool("mq_recv", "Receive and consume messages for an agent. Poll periodically to check for new messages.", {
  name: z.string(),
  msg_type: z.string().optional(),
}, async ({ name, msg_type }) => {
  const msgs = await client.recv(name, msg_type || undefined) as unknown[];
  return { content: msgs.map(m => ({ type: "text" as const, text: JSON.stringify(m) })) };
});

server.tool("mq_ls", "List all registered agents", {}, async () => {
  const agents = await client.ls() as unknown[];
  return { content: agents.map(a => ({ type: "text" as const, text: JSON.stringify(a) })) };
});

server.tool("mq_history", "View delivered message history", {
  limit: z.number().default(20),
}, async ({ limit }) => {
  const msgs = await client.history(limit) as unknown[];
  return { content: msgs.map(m => ({ type: "text" as const, text: JSON.stringify(m) })) };
});

server.tool("mq_login", "Login with a token. Server defaults to config.", {
  token: z.string(),
  server: z.string().optional(),
}, async ({ token, server: srv }) => {
  const cfg = client.loadConfig();
  const finalServer = srv?.replace(/\/+$/, "") || cfg.server;
  client.saveConfig({ server: finalServer, token });
  return { content: [{ type: "text", text: JSON.stringify({ status: "ok", server: finalServer }) }] };
});

server.tool("mq_logout", "Disconnect from server", {}, async () => {
  client.saveConfig({ server: "", token: "" });
  return { content: [{ type: "text", text: JSON.stringify({ status: "ok" }) }] };
});

const transport = new StdioServerTransport();
await server.connect(transport);
