import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { ChildProcess, spawn } from "child_process";
import { join } from "path";
import * as client from "./client.js";

const SERVER_DIR = join(__dirname, "../../server");
const TOKEN = "test-integration-" + Math.random().toString(36).slice(2);
let serverProc: ChildProcess;
let port: number;

async function waitForServer(url: string, retries = 30): Promise<void> {
  for (let i = 0; i < retries; i++) {
    try {
      const res = await fetch(`${url}/healthz`);
      if (res.ok) return;
    } catch {}
    await new Promise(r => setTimeout(r, 200));
  }
  throw new Error("Server did not start");
}

beforeAll(async () => {
  port = 18000 + Math.floor(Math.random() * 1000);
  serverProc = spawn("python3", ["-m", "uvicorn", "app:app", "--port", String(port)], {
    cwd: SERVER_DIR,
    stdio: "pipe",
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" },
  });

  await waitForServer(`http://localhost:${port}`);
  client.saveConfig({ server: `http://localhost:${port}`, token: TOKEN });
}, 15000);

afterAll(() => {
  serverProc?.kill();
});

describe("full flow", () => {
  it("add agent", async () => {
    const result = await client.add("backend", "API dev") as { status: string; name: string };
    expect(result.status).toBe("ok");
    expect(result.name).toBe("backend");
  });

  it("add second agent", async () => {
    const result = await client.add("frontend") as { status: string; name: string };
    expect(result.status).toBe("ok");
  });

  it("ls shows both agents", async () => {
    const agents = await client.ls() as { name: string }[];
    const names = agents.map(a => a.name);
    expect(names).toContain("backend");
    expect(names).toContain("frontend");
  });

  it("send message", async () => {
    const result = await client.send("backend", "hello from frontend", "frontend", "task") as { status: string; to: string };
    expect(result.status).toBe("ok");
    expect(result.to).toBe("backend");
  });

  it("recv by name", async () => {
    const msgs = await client.recv("backend") as { payload: string; from: string; type: string }[];
    expect(msgs.length).toBe(1);
    expect(msgs[0].payload).toBe("hello from frontend");
    expect(msgs[0].from).toBe("frontend");
    expect(msgs[0].type).toBe("task");
  });

  it("recv again returns empty (consumed)", async () => {
    const msgs = await client.recv("backend") as unknown[];
    expect(msgs.length).toBe(0);
  });

  it("history shows consumed messages", async () => {
    const msgs = await client.history(50) as { payload: string }[];
    expect(msgs.length).toBeGreaterThan(0);
    expect(msgs.some(m => m.payload === "hello from frontend")).toBe(true);
  });

  it("send with reply_to", async () => {
    await client.send("backend", "response", "frontend", "response", "normal", "orig-123");
    const msgs = await client.recv("backend") as { reply_to?: string }[];
    expect(msgs[0].reply_to).toBe("orig-123");
  });

  it("send to nonexistent target fails", async () => {
    await expect(client.send("nobody", "hi", "frontend")).rejects.toThrow("not found");
  });

  it("unicode message round-trip", async () => {
    const payload = "你好世界 🌍 café";
    await client.send("backend", payload, "frontend");
    const msgs = await client.recv("backend") as { payload: string }[];
    expect(msgs[0].payload).toBe(payload);
  });
});

describe("isolation", () => {
  it("different token cannot see agents", async () => {
    const original = client.loadConfig();
    client.saveConfig({ server: original.server, token: "other-token-" + Math.random().toString(36).slice(2) });

    const agents = await client.ls() as unknown[];
    expect(agents.length).toBe(0);

    client.saveConfig(original);
  });
});
