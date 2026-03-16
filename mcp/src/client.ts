/**
 * agent-mq HTTP client — talks to the cloud server.
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync } from "fs";
import { join } from "path";
import { homedir } from "os";

const VERSION = "0.1.6";
const CONFIG_DIR = join(homedir(), ".agent-mq");
const CONFIG_FILE = join(CONFIG_DIR, "config.json");

export interface Config {
  server: string;
  token: string;
}

export function loadConfig(): Config {
  const defaults: Config = { server: "", token: "" };
  try {
    if (existsSync(CONFIG_FILE)) {
      return { ...defaults, ...JSON.parse(readFileSync(CONFIG_FILE, "utf-8")) };
    }
  } catch {}
  return defaults;
}

export function saveConfig(cfg: Config): void {
  mkdirSync(CONFIG_DIR, { recursive: true });
  writeFileSync(CONFIG_FILE, JSON.stringify(cfg, null, 2));
}

async function api(method: string, path: string, body?: unknown): Promise<unknown> {
  const cfg = loadConfig();
  if (!cfg.server) throw new Error("Server URL not configured. Run `mq login` first.");

  const url = `${cfg.server}/api/v1${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "User-Agent": `agent-mq/${VERSION}`,
  };
  if (cfg.token) headers["Authorization"] = `Bearer ${cfg.token}`;

  const res = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const err = await res.json() as { detail?: string };
      if (err.detail) detail = err.detail;
    } catch {}
    throw new Error(detail);
  }

  return res.json();
}

export async function add(name: string, desc = "", tool = "claude-code") {
  return api("POST", "/agents", { name, desc, tool });
}

export async function send(
  target: string,
  message: string,
  sender: string,
  msgType = "text",
  priority = "normal",
  replyTo?: string,
) {
  const body: Record<string, string> = {
    target, message, from: sender, type: msgType, priority,
  };
  if (replyTo) body.reply_to = replyTo;
  return api("POST", "/send", body);
}

export async function recv(name?: string, msgType?: string) {
  const params = msgType ? `?type=${msgType}` : "";
  const path = name ? `/recv/${name}${params}` : `/recv${params}`;
  return api("GET", path);
}

export async function ls() {
  return api("GET", "/agents");
}

export async function history(limit = 20) {
  return api("GET", `/history?limit=${limit}`);
}
