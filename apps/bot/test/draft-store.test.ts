import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DraftStore } from "../src/draft-store.js";
import type { DraftSlip } from "@safe-picks/contracts";

function makeDraft(overrides: Partial<DraftSlip> = {}): DraftSlip {
  return {
    targetOdds: 3.0,
    maxLegs: 3,
    candidates: [],
    combinedOdds: 0,
    estimatedJointProbability: 0,
    status: "abstain",
    warnings: [],
    ...overrides,
  };
}

let tmpDir = "";

beforeAll(async () => { tmpDir = await mkdtemp(join(tmpdir(), "draft-store-test-")); });
afterAll(async () => { await rm(tmpDir, { recursive: true, force: true }); });

describe("DraftStore", () => {
  it("returns undefined when no draft exists", async () => {
    const store = new DraftStore(tmpDir);
    expect(await store.get(999)).toBeUndefined();
  });

  it("set then get round-trips the draft", async () => {
    const store = new DraftStore(tmpDir);
    const draft = makeDraft({ targetOdds: 2.5, maxLegs: 2, warnings: ["test warning"] });
    await store.set(42, draft);
    expect(await store.get(42)).toEqual(draft);
  });

  it("set overwrites an existing draft", async () => {
    const store = new DraftStore(tmpDir);
    await store.set(1, makeDraft({ targetOdds: 1.5 }));
    await store.set(1, makeDraft({ targetOdds: 4.0 }));
    expect((await store.get(1))?.targetOdds).toBe(4.0);
  });

  it("isolates drafts by chat ID", async () => {
    const store = new DraftStore(tmpDir);
    await store.set(10, makeDraft({ targetOdds: 2.0 }));
    await store.set(20, makeDraft({ targetOdds: 5.0 }));
    expect((await store.get(10))?.targetOdds).toBe(2.0);
    expect((await store.get(20))?.targetOdds).toBe(5.0);
  });

  it("delete removes the draft", async () => {
    const store = new DraftStore(tmpDir);
    await store.set(77, makeDraft());
    await store.delete(77);
    expect(await store.get(77)).toBeUndefined();
  });

  it("a new instance reads the persisted file (simulates restart)", async () => {
    const store1 = new DraftStore(tmpDir);
    await store1.set(55, makeDraft({ targetOdds: 7.77 }));
    const store2 = new DraftStore(tmpDir);
    expect((await store2.get(55))?.targetOdds).toBe(7.77);
  });
});
