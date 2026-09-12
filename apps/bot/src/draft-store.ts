import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import type { DraftSlip } from "@safe-picks/contracts";

/**
 * Persists each user's current draft slip to an individual JSON file.
 * Writes are atomic (tmp write + rename) so a crash never corrupts an
 * existing draft.
 */
export class DraftStore {
  constructor(private readonly dir: string) {}

  async get(chatId: number): Promise<DraftSlip | undefined> {
    try {
      const raw = await readFile(this._path(chatId), "utf8");
      const parsed: unknown = JSON.parse(raw);
      if (parsed && typeof parsed === "object" && "candidates" in parsed) {
        return parsed as DraftSlip;
      }
    } catch {
      // File missing or malformed — treat as no draft.
    }
    return undefined;
  }

  async set(chatId: number, draft: DraftSlip): Promise<void> {
    const path = this._path(chatId);
    const tmp = `${path}.tmp`;
    await mkdir(dirname(path), { recursive: true });
    await writeFile(tmp, JSON.stringify(draft), "utf8");
    await rename(tmp, path);
  }

  async delete(chatId: number): Promise<void> {
    const { unlink } = await import("node:fs/promises");
    try {
      await unlink(this._path(chatId));
    } catch {
      // Already gone — fine.
    }
  }

  private _path(chatId: number): string {
    return join(this.dir, `${chatId}.json`);
  }
}
