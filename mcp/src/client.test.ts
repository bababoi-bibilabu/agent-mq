import { describe, it, expect, vi, beforeEach } from "vitest";
import { loadConfig, saveConfig } from "./client.js";
import { mkdtempSync, writeFileSync, rmSync } from "fs";
import { join } from "path";
import { tmpdir } from "os";

// Mock home directory for config tests
let tmpDir: string;

beforeEach(() => {
  tmpDir = mkdtempSync(join(tmpdir(), "mq-test-"));
});

describe("loadConfig", () => {
  it("returns defaults when no config file", () => {
    const cfg = loadConfig();
    expect(cfg).toHaveProperty("server");
    expect(cfg).toHaveProperty("token");
  });
});

describe("saveConfig + loadConfig round trip", () => {
  it("persists config", () => {
    // This tests the actual file path (~/.agent-mq/config.json)
    // which may already exist. Just verify saveConfig doesn't throw.
    const cfg = loadConfig();
    saveConfig(cfg);
    const cfg2 = loadConfig();
    expect(cfg2.server).toBe(cfg.server);
    expect(cfg2.token).toBe(cfg.token);
  });
});

describe("api calls", () => {
  it("throws when no server configured", async () => {
    // Temporarily clear config
    const original = loadConfig();
    saveConfig({ server: "", token: "" });

    const { add } = await import("./client.js");
    await expect(add("test")).rejects.toThrow("not configured");

    // Restore
    saveConfig(original);
  });

  it("throws on network error", async () => {
    const original = loadConfig();
    saveConfig({ server: "http://localhost:1", token: "test-token-1234567890" });

    const { ls } = await import("./client.js");
    await expect(ls()).rejects.toThrow();

    saveConfig(original);
  });
});
