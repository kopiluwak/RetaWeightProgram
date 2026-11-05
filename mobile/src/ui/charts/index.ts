// Barrel for the hand-rolled SVG chart kit used by the analytics screens.
export { default as LineChart } from "./LineChart";
export type { LinePoint } from "./LineChart";
export { default as WeeklyBars } from "./WeeklyBars";
export type { Bar } from "./WeeklyBars";
export { default as CalendarHeatmap } from "./CalendarHeatmap";
export type { HeatDay } from "./CalendarHeatmap";
export { default as Donut } from "./Donut";
export type { DonutSlice } from "./Donut";

import type { Theme } from "../../theme";

/** Stable color assignment for muscle-group slices, drawn from the theme. */
export function musclePalette(theme: Theme): string[] {
  return [
    theme.colors.accent,
    theme.colors.secondary,
    theme.colors.success,
    theme.colors.warning,
    theme.colors.danger,
    theme.colors.textTertiary,
    theme.dark ? "#8E7CC3" : "#674EA7",
    theme.dark ? "#6FA8DC" : "#3D85C6",
    theme.dark ? "#C27BA0" : "#A64D79",
    theme.dark ? "#93C47D" : "#38761D",
    theme.colors.textSecondary,
  ];
}
