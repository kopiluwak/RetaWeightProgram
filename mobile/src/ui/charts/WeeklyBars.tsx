import React, { useState } from "react";
import { Text, View } from "react-native";
import Svg, { Rect } from "react-native-svg";
import { useTheme } from "../../theme";

export type Bar = { label: string; value: number; highlight?: boolean };

/**
 * Compact bar chart (weekly volume / workouts-per-week mini-bars).
 * Highlighted bars use the accent color; the rest a muted fill.
 */
export default function WeeklyBars({
  bars,
  height = 72,
  width,
  maxValue,
  showLabels = false,
  formatValue = (v: number) => String(Math.round(v)),
}: {
  bars: Bar[];
  height?: number;
  width?: number;
  /** Optional fixed scale (e.g. the weekly target) so bars compare against it. */
  maxValue?: number;
  showLabels?: boolean;
  formatValue?: (v: number) => string;
}) {
  const theme = useTheme();
  const [w, setW] = useState(width ?? 0);
  const [selected, setSelected] = useState<number | null>(null);

  const max = Math.max(maxValue ?? 0, ...bars.map((b) => b.value), 1);
  const gap = 4;
  const barW = w > 0 && bars.length > 0 ? (w - gap * (bars.length - 1)) / bars.length : 0;

  return (
    <View onLayout={(e) => !width && setW(e.nativeEvent.layout.width)}>
      {selected != null && bars[selected] && (
        <Text style={{ ...theme.typography.footnote, color: theme.colors.textSecondary, marginBottom: 2 }}>
          {bars[selected].label}: {formatValue(bars[selected].value)}
        </Text>
      )}
      {w > 0 && bars.length > 0 && (
        <View
          onStartShouldSetResponder={() => true}
          onResponderGrant={(e) => {
            const i = Math.min(bars.length - 1, Math.max(0, Math.floor(e.nativeEvent.locationX / (barW + gap))));
            setSelected(i);
          }}
        >
          <Svg width={w} height={height}>
            {bars.map((b, i) => {
              const h = Math.max(2, (b.value / max) * (height - 4));
              return (
                <Rect
                  key={i}
                  x={i * (barW + gap)}
                  y={height - h}
                  width={barW}
                  height={h}
                  rx={Math.min(4, barW / 3)}
                  fill={
                    b.highlight || i === selected
                      ? theme.colors.accent
                      : b.value > 0
                        ? theme.colors.secondary
                        : theme.colors.backgroundElevated2
                  }
                  opacity={b.highlight || i === selected ? 1 : 0.75}
                />
              );
            })}
          </Svg>
        </View>
      )}
      {showLabels && bars.length > 0 && (
        <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 2 }}>
          <Text style={{ ...theme.typography.caption, color: theme.colors.textTertiary }}>{bars[0].label}</Text>
          <Text style={{ ...theme.typography.caption, color: theme.colors.textTertiary }}>
            {bars[bars.length - 1].label}
          </Text>
        </View>
      )}
    </View>
  );
}
