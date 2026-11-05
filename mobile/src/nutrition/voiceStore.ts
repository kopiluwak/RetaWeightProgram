/**
 * Neutron voice-log: on-device persistence (expo-sqlite).
 *
 * Two tiny tables in one local DB:
 *   alias_cache — phrase_norm -> protein estimate. Rows come from (a) user
 *     corrections on the review screen (source 'correction', always wins) and
 *     (b) answers from /nutrition/parse (source 'ai'). This is what makes the
 *     module cache-first: a phrase that has ever been corrected or AI-parsed
 *     resolves locally, instantly, offline, forever.
 *   log_queue — protein logs made while offline, flushed on next open/log.
 *
 * The cache is mirrored into memory on init so the parser's lookup stays
 * synchronous (it runs per keystroke/utterance). A few thousand rows of
 * (short string -> 4 numbers) is well under 1 MB — no eviction needed; if it
 * ever matters, prune by updated_at.
 */

import * as SQLite from "expo-sqlite";
import { CachedEstimate } from "./parser";
import { normalize } from "./matcher";

let db: SQLite.SQLiteDatabase | null = null;
let mem: Map<string, CachedEstimate> = new Map();
let ready = false;

/** Open the DB, create tables if needed, and mirror alias_cache into memory. */
export async function initVoiceStore(): Promise<void> {
  if (ready) return;
  db = await SQLite.openDatabaseAsync("neutron_voicelog.db");
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS alias_cache (
      phrase_norm TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      protein_per_100g REAL NOT NULL,
      portion_est_g REAL NOT NULL,
      source TEXT NOT NULL,
      updated_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS log_queue (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      grams REAL NOT NULL,
      calories REAL,
      label TEXT NOT NULL,
      source TEXT NOT NULL,
      tz_minutes INTEGER NOT NULL,
      created_at INTEGER NOT NULL
    );
  `);
  const rows = await db.getAllAsync<{
    phrase_norm: string; name: string; protein_per_100g: number;
    portion_est_g: number; source: string;
  }>("SELECT phrase_norm, name, protein_per_100g, portion_est_g, source FROM alias_cache");
  mem = new Map(rows.map((r) => [r.phrase_norm, {
    name: r.name, proteinPer100g: r.protein_per_100g,
    portionEstG: r.portion_est_g,
    source: (r.source === "correction" ? "correction" : "ai") as "correction" | "ai",
  }]));
  ready = true;
}

/** Synchronous lookup for the parser (tier 1). */
export function cacheLookup(phraseNorm: string): CachedEstimate | null {
  return mem.get(phraseNorm) ?? null;
}

/** Corrections beat AI answers; AI answers never overwrite corrections. */
export async function cachePut(phrase: string, est: CachedEstimate): Promise<void> {
  const norm = normalize(phrase);
  if (!norm) return;
  const existing = mem.get(norm);
  if (existing?.source === "correction" && est.source === "ai") return;
  mem.set(norm, est);
  if (!db) return;
  await db.runAsync(
    `INSERT INTO alias_cache (phrase_norm, name, protein_per_100g, portion_est_g, source, updated_at)
     VALUES (?, ?, ?, ?, ?, ?)
     ON CONFLICT(phrase_norm) DO UPDATE SET
       name=excluded.name, protein_per_100g=excluded.protein_per_100g,
       portion_est_g=excluded.portion_est_g, source=excluded.source,
       updated_at=excluded.updated_at`,
    norm, est.name, est.proteinPer100g, est.portionEstG, est.source, Date.now(),
  );
}

// ------------------------------------------------------------- log queue

export interface QueuedLog {
  id: number;
  grams: number;
  calories: number | null;
  label: string;
  source: string;
  tzMinutes: number;
}

/** Queue a protein log made offline; flushed on the next app open or log. */
export async function enqueueLog(entry: Omit<QueuedLog, "id">): Promise<void> {
  if (!db) await initVoiceStore();
  await db!.runAsync(
    "INSERT INTO log_queue (grams, calories, label, source, tz_minutes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
    entry.grams, entry.calories, entry.label, entry.source, entry.tzMinutes, Date.now(),
  );
}

/** Number of logs still waiting to be flushed (drives the offline banner). */
export async function pendingLogCount(): Promise<number> {
  if (!db) await initVoiceStore();
  const row = await db!.getFirstAsync<{ n: number }>("SELECT COUNT(*) AS n FROM log_queue");
  return row?.n ?? 0;
}

/** Attempt to send every queued log; delete the ones that succeed. Stops at
 * the first network-ish failure (leaves the rest queued). Returns #sent. */
export async function flushLogQueue(
  send: (e: QueuedLog) => Promise<void>,
): Promise<number> {
  if (!db) await initVoiceStore();
  const rows = await db!.getAllAsync<QueuedLog & { tz_minutes: number }>(
    "SELECT id, grams, calories, label, source, tz_minutes AS tzMinutes FROM log_queue ORDER BY id",
  );
  let sent = 0;
  for (const row of rows) {
    try {
      await send(row);
      await db!.runAsync("DELETE FROM log_queue WHERE id = ?", row.id);
      sent += 1;
    } catch {
      break; // still offline (or server down) — retry on next flush
    }
  }
  return sent;
}
