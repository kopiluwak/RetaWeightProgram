// Client mirror of the backend taxonomy (app/equipment.py). Used by the
// confirmation screen's type picker.
export const EQUIPMENT_TYPES = [
  "barbell",
  "plates",
  "fixed_dumbbells",
  "adjustable_dumbbells",
  "kettlebell",
  "bench_flat",
  "bench_adjustable",
  "squat_stand",
  "power_rack",
  "pull_up_bar",
  "cable_machine",
  "selectorized_machine",
  "smith_machine",
  "resistance_bands",
  "bodyweight_only",
  "treadmill",
  "rowing_machine",
  "stationary_bike",
  "elliptical",
  "cardio_other",
  "other",
] as const;

// Cardio machines are stored but never used by the strength engine (mirror of
// app/equipment.py CARDIO_TYPES) — excluded from the customization picker.
export const CARDIO_TYPES: ReadonlySet<string> = new Set([
  "treadmill",
  "rowing_machine",
  "stationary_bike",
  "elliptical",
  "cardio_other",
]);

/** True for equipment types the strength engine can actually program with. */
export function isStrengthType(t: string): boolean {
  return !CARDIO_TYPES.has(t) && t !== "bodyweight_only" && t !== "other";
}

/** "power_rack" -> "Power Rack" for display. */
export function prettyType(t: string): string {
  return t.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
