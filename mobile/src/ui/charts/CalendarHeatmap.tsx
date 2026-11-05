import React, { useMemo, useState } from "react";
import { Text, View } from "react-native";
import Svg, { Rect } from "react-native-svg";
import { useTheme } from "../../theme";

export type HeatDay = { date: string; sets: number };

/**
 * GitHub-style training heatmap: columns are weeks (Mon-start), rows are
 * days. Cell intensity = sets logged that day (spec S5). Tapping a cell
 * reports the date to the parent (used to filter the history list).
 */
export default function CalendarHeatmap({
  days,
  weeks = 26,
  onDayPress,
  width,
}: {
  days: HeatDay[];
  weeks?: number;
  onDayPress?: (date: string) => void;
  width?: number;
}) {
  const theme = useTheme();
  const [w, setW] = useState(width ?? 0);
  const [selected, setSelected] = useState<string | null>(null);

  const grid = useMemo(() => {
    const bySets = new Map(days.map((d) => [d.date, d.sets]));
    const today = new Date();
    const monday = new Date(today);
    monday.setDate(today.getDate() - ((today.getDay() + 6) % 7)); // this week's Monday
    const cols: { date: string; sets: number; future: boolean }[][] = [];
    const monthMarks: { col: number; label: string }[] = [];
    let lastMonth = -1;
    for (let c = 0; c < weeks; c++) {
      const weekStart = new Date(monday);
      weekStart.setDate(monday.getDate() - (weeks - 1 - c) * 7);
      if (weekStart.getMonth() !== lastMonth) {
        lastMonth = weekStart.getMonth();
        monthMarks.push({ col: c, label: weekStart.toLocaleDateString(undefined, { month: "short" }) });
      }
      const col: { date: string; sets: number; future: boolean }[] = [];
      for (let r = 0; r < 7; r++) {
        const d = new Date(weekStart);
        d.setDate(weekStart.getDate() + r);
        const iso = d.toISOString().slice(0, 10);
        col.push({ date: iso, sets: bySets.get(iso) ?? 0, future: d > today });
      }
      cols.push(col);
    }
    return { cols, monthMarks };
  }, [days, weeks]);

  const cell = w > 0 ? Math.floor((w - (weeks - 1) * 2) / weeks) : 0;
  const gap = 2;
  const gridH = cell * 7 + gap * 6;

  // Intensity ramp: 0 -> muted, then 3 accent steps.
  const ramp = (sets: number, future: boolean): { color: string; opacity: number } => {
    if (future) return { color: "transparent", opacity: 0 };
    if (sets === 0) return { color: theme.colors.backgroundElevated2, opacity: 1 };
    if (sets <= 8) return { color: theme.colors.accent, opacity: 0.35 };
    if (sets <= 16) return { color: theme.colors.accent, opacity: 0.65 };
    return { color: theme.colors.accent, opacity: 1 };
  };

  const selectedDay = selected ? grid.cols.flat().find((d) => d.date === selected) : null;

  return (
    <View onLayout={(e) => !width && setW(e.nativeEvent.layout.width)}>
      {w > 0 && cell > 0 && (
        <>
          <View style={{ height: 16 }}>
            {grid.monthMarks.map((m, i) => (
              <Text
                key={i}
                style={{
                  position: "absolute",
                  left: m.col * (cell + gap),
                  ...theme.typography.caption,
                  color: theme.colors.textTertiary,
                }}
              >
                {m.label}
              </Text>
            ))}
          </View>
          <View
            onStartShouldSetResponder={() => true}
            onResponderGrant={(e) => {
              const { locationX, locationY } = e.nativeEvent;
              const c = Math.min(weeks - 1, Math.max(0, Math.floor(locationX / (cell + gap))));
              const r = Math.min(6, Math.max(0, Math.floor(locationY / (cell + gap))));
              const d = grid.cols[c]?.[r];
              if (d && !d.future) {
                setSelected(d.date);
                onDayPress?.(d.date);
              }
            }}
          >
            <Svg width={w} height={gridH}>
              {grid.cols.map((col, c) =>
                col.map((d, r) => {
                  const { color, opacity } = ramp(d.sets, d.future);
                  return (
                    <Rect
                      key={`${c}-${r}`}
                      x={c * (cell + gap)}
                      y={r * (cell + gap)}
                      width={cell}
                      height={cell}
                      rx={2}
                      fill={color}
                      opacity={opacity}
                      stroke={d.date === selected ? theme.colors.text : "none"}
                      strokeWidth={d.date === selected ? 1.5 : 0}
                    />
                  );
                }),
              )}
            </Svg>
          </View>
          <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 4 }}>
            <Text style={{ ...theme.typography.caption, color: theme.colors.textTertiary }}>
              {selectedDay
                ? `${new Date(selectedDay.date + "T12:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" })} — ${selectedDay.sets} set${selectedDay.sets === 1 ? "" : "s"}`
                : "Tap a day for details"}
            </Text>
            <Text style={{ ...theme.typography.caption, color: theme.colors.textTertiary }}>less → more</Text>
          </View>
        </>
      )}
    </View>
  );
}
