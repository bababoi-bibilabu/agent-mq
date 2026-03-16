import { describe, it, expect, beforeAll, afterAll } from "vitest";
import * as client from "./client.js";

const REMOTE_SERVER = "https://api.agent-mq.com";
const TOKEN = "test-remote-" + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
let originalConfig: client.Config;

beforeAll(async () => {
  originalConfig = client.loadConfig();
  const res = await fetch(`${REMOTE_SERVER}/healthz`);
  if (!res.ok) throw new Error("Remote server not available, skipping");
  client.saveConfig({ server: REMOTE_SERVER, token: TOKEN });
});

afterAll(() => {
  client.saveConfig(originalConfig);
});

describe("remote API", () => {
  it("add agent", async () => {
    const result = await client.add("remote-test") as { status: string; name: string };
    expect(result.status).toBe("ok");
    expect(result.name).toBe("remote-test");
  });

  it("ls", async () => {
    const agents = await client.ls() as { name: string }[];
    expect(agents.some(a => a.name === "remote-test")).toBe(true);
  });

  it("send + recv", async () => {
    await client.send("remote-test", "hello from remote test", "remote-test");
    const msgs = await client.recv("remote-test") as { payload: string }[];
    expect(msgs.length).toBe(1);
    expect(msgs[0].payload).toBe("hello from remote test");
  });

  it("history", async () => {
    const msgs = await client.history() as { payload: string }[];
    expect(msgs.some(m => m.payload === "hello from remote test")).toBe(true);
  });

  it("recv empty after consume", async () => {
    const msgs = await client.recv("remote-test") as unknown[];
    expect(msgs.length).toBe(0);
  });
});
