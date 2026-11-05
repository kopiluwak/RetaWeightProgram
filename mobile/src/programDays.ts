// Which training day should the user land on when they open a program screen?
//
// Rule: the day AFTER the most recently completed session, wrapping around, so
// finishing "Push" leaves you on "Pull" next time instead of back on Day 1.
// ProgramScreen had this inline; CouchProgramScreen never did, which is why the
// beginner view always reopened on the first day. Shared here so the two screens
// can't drift apart again.
import { WorkoutApi, WorkoutHistoryItem } from "./api";

/**
 * Index of the day to open, or `null` when there's nothing to go on (no days,
 * no completed session yet, or the logged day no longer exists in the program).
 * `null` means "leave the current selection alone" — never guess.
 *
 * Matching prefers the session's `day_index`, which is exact. That field is a
 * recent addition to `/workouts/history`, so it is absent against an older
 * backend; we then fall back to matching the day NAME, which is what
 * ProgramScreen has always done. Day names are distinct per the engine's
 * Push/Pull/Legs split, so the fallback is sound — it only breaks if the
 * program was regenerated into a different split since that session, and
 * `findIndex` returning -1 there correctly yields `null`.
 */
export function dayAfterLastCompleted(
  days: { name: string }[],
  history: WorkoutHistoryItem[],
): number | null {
  if (days.length === 0) return null;
  const lastDone = history.find((h) => h.status === "completed");
  if (!lastDone) return null;

  const byIndex = lastDone.day_index;
  const idx =
    typeof byIndex === "number" && byIndex >= 0 && byIndex < days.length
      ? byIndex
      : days.findIndex((d) => d.name === lastDone.day_name);
  if (idx < 0) return null;

  return (idx + 1) % days.length;
}

/**
 * Best-effort wrapper: fetch history and compute the next day. Never throws —
 * this is a convenience, so a failed history call just leaves the caller's
 * current day selection in place.
 */
export async function nextDayIndex(days: { name: string }[]): Promise<number | null> {
  try {
    return dayAfterLastCompleted(days, await WorkoutApi.history());
  } catch {
    return null;
  }
}
