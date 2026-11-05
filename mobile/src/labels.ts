// Human-facing labels for internal enum values so screens never render raw
// engine vocabulary (e.g. "conservative") to the user. See usability review.

/** Options for the experience picker (also the source of pretty labels). */
export const EXPERIENCE_OPTIONS: { key: string; label: string }[] = [
  { key: "beginner", label: "New to lifting" },
  { key: "conservative", label: "Returning / cautious" },
  { key: "intermediate", label: "Intermediate" },
  { key: "advanced", label: "Advanced" },
];

const EXPERIENCE_LABELS: Record<string, string> =
  Object.fromEntries(EXPERIENCE_OPTIONS.map((o) => [o.key, o.label]));

/** "conservative" -> "Returning / cautious"; unknown values are title-cased. */
export function prettyExperience(key: string): string {
  return (
    EXPERIENCE_LABELS[key] ??
    key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

/** One-line gloss for the RIR term, shown near where it's first used. */
export const RIR_HINT = "RIR = reps in reserve: how many more you could have done.";

/** The splits the program engine can build (engine.py `_TEMPLATES`). */
export const DAY_OPTIONS = [3, 4, 5];

/**
 * Short muscle-group label for a training day, used by day tabs and pickers.
 *
 * The engine names days "Push — Chest, Shoulders & Triceps" / "Arms — Biceps &
 * Triceps"; the part before the em dash is the muscle-group headline the user
 * actually thinks in ("Push", "Legs", "Arms"). Names with no dash ("Shoulders
 * & Arms") are already short and pass through unchanged. Falls back to "Day N"
 * so an unnamed day still gets a usable label.
 *
 * This is what lets a user say "not legs today — arms": the day tabs used to
 * read "Day 1 / Day 2 / Day 3", which told them nothing about what they were
 * about to train.
 */
export function dayShortLabel(name: string, index: number): string {
  const head = (name || "").split(/\s+[—–-]\s+/)[0].trim();
  return head || `Day ${index + 1}`;
}
