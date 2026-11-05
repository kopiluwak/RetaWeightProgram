import React from "react";
import { Text, View } from "react-native";
import Svg, { Circle, G, Path } from "react-native-svg";
import { useTheme } from "../../theme";

export type DonutSlice = { label: string; value: number; color: string };

/** SVG path for one circular arc segment (stroked, not filled). */
function arcPath(cx: number, cy: number, r: number, start: number, end: number): string {
  // start/end in radians, clockwise from 12 o'clock.
  const sx = cx + r * Math.sin(start);
  const sy = cy - r * Math.cos(start);
  const ex = cx + r * Math.sin(end);
  const ey = cy - r * Math.cos(end);
  const large = end - start > Math.PI ? 1 : 0;
  return `M${sx.toFixed(2)},${sy.toFixed(2)} A${r},${r} 0 ${large} 1 ${ex.toFixed(2)},${ey.toFixed(2)}`;
}

/**
 * Donut chart with legend (muscle-focus volume split, spec S2 card 5).
 * Slices under 1% are dropped; a single-slice donut renders as a full ring.
 */
export default function Donut({
  slices,
  size = 148,
  strokeWidth = 22,
  centerLabel,
  centerSub,
}: {
  slices: DonutSlice[];
  size?: number;
  strokeWidth?: number;
  centerLabel?: string;
  centerSub?: string;
}) {
  const theme = useTheme();
  const total = slices.reduce((a, s) => a + s.value, 0);
  const visible = slices.filter((s) => total > 0 && s.value / total >= 0.01);
  const r = (size - strokeWidth) / 2;
  const cx = size / 2;
  const cy = size / 2;

  let angle = 0;
  const gapRad = visible.length > 1 ? 0.03 : 0;

  return (
    <View style={{ flexDirection: "row", alignItems: "center" }}>
      <View style={{ width: size, height: size, alignItems: "center", justifyContent: "center" }}>
        <Svg width={size} height={size}>
          {visible.length === 0 && (
            <Circle cx={cx} cy={cy} r={r} stroke={theme.colors.backgroundElevated2} strokeWidth={strokeWidth} fill="none" />
          )}
          <G>
            {visible.map((s, i) => {
              const frac = s.value / total;
              const start = angle + gapRad / 2;
              const end = angle + frac * 2 * Math.PI - gapRad / 2;
              angle += frac * 2 * Math.PI;
              if (frac >= 0.999) {
                return (
                  <Circle key={i} cx={cx} cy={cy} r={r} stroke={s.color} strokeWidth={strokeWidth} fill="none" />
                );
              }
              return (
                <Path
                  key={i}
                  d={arcPath(cx, cy, r, start, Math.max(end, start + 0.02))}
                  stroke={s.color}
                  strokeWidth={strokeWidth}
                  fill="none"
                  strokeLinecap="butt"
                />
              );
            })}
          </G>
        </Svg>
        {centerLabel != null && (
          <View style={{ position: "absolute", alignItems: "center" }}>
            <Text style={{ ...theme.typography.headline, color: theme.colors.text }}>{centerLabel}</Text>
            {centerSub != null && (
              <Text style={{ ...theme.typography.caption, color: theme.colors.textTertiary }}>{centerSub}</Text>
            )}
          </View>
        )}
      </View>
      <View style={{ flex: 1, marginLeft: theme.spacing.lg }}>
        {visible.map((s, i) => (
          <View key={i} style={{ flexDirection: "row", alignItems: "center", marginBottom: 4 }}>
            <View style={{ width: 10, height: 10, borderRadius: 3, backgroundColor: s.color, marginRight: 8 }} />
            <Text style={{ ...theme.typography.footnote, color: theme.colors.text, flex: 1 }} numberOfLines={1}>
              {s.label}
            </Text>
            <Text style={{ ...theme.typography.footnote, color: theme.colors.textSecondary }}>
              {total > 0 ? Math.round((s.value / total) * 100) : 0}%
            </Text>
          </View>
        ))}
        {visible.length === 0 && (
          <Text style={{ ...theme.typography.footnote, color: theme.colors.textTertiary }}>
            Log some weighted sets to see your split.
          </Text>
        )}
      </View>
    </View>
  );
}
