import React, { useMemo, useState } from "react";
import { Text, View } from "react-native";
import Svg, { Circle, Defs, LinearGradient, Path, Stop } from "react-native-svg";
import { useTheme } from "../../theme";

export type LinePoint = { date: string; value: number };

/**
 * Time-scaled line chart with an area fill and tap-to-inspect.
 * Hand-rolled on react-native-svg (spec F3-revision): x positions follow real
 * date spacing, y is padded min..max. Tapping selects the nearest point and
 * shows a marker + a value/date readout above the chart.
 */
export default function LineChart({
  points,
  height = 160,
  width,
  color,
  formatValue = (v: number) => String(Math.round(v * 10) / 10),
}: {
  points: LinePoint[];
  height?: number;
  /** Measured by parent; falls back to onLayout. */
  width?: number;
  color?: string;
  formatValue?: (v: number) => string;
}) {
  const theme = useTheme();
  const stroke = color ?? theme.colors.accent;
  const [w, setW] = useState(width ?? 0);
  const [selected, setSelected] = useState<number | null>(null);

  const pad = { top: 8, bottom: 8, left: 6, right: 6 };

  const geom = useMemo(() => {
    if (!w || points.length === 0) return null;
    const xs = points.map((p) => new Date(p.date).getTime());
    const ys = points.map((p) => p.value);
    const x0 = Math.min(...xs);
    const x1 = Math.max(...xs);
    const yMin = Math.min(...ys);
    const yMax = Math.max(...ys);
    const ySpan = yMax - yMin || 1;
    const innerW = w - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const X = (t: number) => pad.left + (x1 === x0 ? innerW / 2 : ((t - x0) / (x1 - x0)) * innerW);
    const Y = (v: number) => pad.top + innerH - ((v - yMin) / ySpan) * innerH;
    const pts = points.map((p, i) => ({ x: X(xs[i]), y: Y(p.value) }));
    const line = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
    const area = `${line} L${pts[pts.length - 1].x.toFixed(1)},${height - pad.bottom} L${pts[0].x.toFixed(1)},${height - pad.bottom} Z`;
    return { pts, line, area, yMin, yMax };
  }, [w, points, height]);

  const onTouch = (locationX: number) => {
    if (!geom) return;
    let best = 0;
    let dist = Infinity;
    geom.pts.forEach((p, i) => {
      const d = Math.abs(p.x - locationX);
      if (d < dist) {
        dist = d;
        best = i;
      }
    });
    setSelected(best);
  };

  const sel = selected != null && points[selected] ? points[selected] : null;

  return (
    <View onLayout={(e) => !width && setW(e.nativeEvent.layout.width)}>
      <View style={{ minHeight: 20, marginBottom: 2 }}>
        {sel ? (
          <Text style={{ ...theme.typography.subhead, color: theme.colors.text }}>
            {formatValue(sel.value)}
            <Text style={{ color: theme.colors.textTertiary }}>
              {"  "}
              {new Date(sel.date).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
            </Text>
          </Text>
        ) : points.length > 0 ? (
          <Text style={{ ...theme.typography.footnote, color: theme.colors.textTertiary }}>
            Tap the chart to inspect a session
          </Text>
        ) : null}
      </View>
      {points.length === 0 ? (
        <View style={{ height, alignItems: "center", justifyContent: "center" }}>
          <Text style={{ ...theme.typography.footnote, color: theme.colors.textTertiary }}>
            Not enough data yet — keep logging.
          </Text>
        </View>
      ) : (
        <View
          onStartShouldSetResponder={() => true}
          onResponderGrant={(e) => onTouch(e.nativeEvent.locationX)}
          onResponderMove={(e) => onTouch(e.nativeEvent.locationX)}
        >
          {w > 0 && geom && (
            <Svg width={w} height={height}>
              <Defs>
                <LinearGradient id="lc-fill" x1="0" y1="0" x2="0" y2="1">
                  <Stop offset="0" stopColor={stroke} stopOpacity={theme.dark ? 0.35 : 0.22} />
                  <Stop offset="1" stopColor={stroke} stopOpacity={0.02} />
                </LinearGradient>
              </Defs>
              <Path d={geom.area} fill="url(#lc-fill)" />
              <Path d={geom.line} stroke={stroke} strokeWidth={2.5} fill="none" strokeLinejoin="round" strokeLinecap="round" />
              {geom.pts.map((p, i) => (
                <Circle
                  key={i}
                  cx={p.x}
                  cy={p.y}
                  r={i === selected ? 5 : geom.pts.length <= 40 ? 3 : 0}
                  fill={i === selected ? stroke : theme.colors.backgroundElevated}
                  stroke={stroke}
                  strokeWidth={1.5}
                />
              ))}
            </Svg>
          )}
        </View>
      )}
      {points.length > 0 && (
        <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
          <Text style={{ ...theme.typography.caption, color: theme.colors.textTertiary }}>
            {new Date(points[0].date).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
          </Text>
          <Text style={{ ...theme.typography.caption, color: theme.colors.textTertiary }}>
            {new Date(points[points.length - 1].date).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
          </Text>
        </View>
      )}
    </View>
  );
}
