// Weekly progress badge with completion-based shading (spec: gamification).
// The fill deepens with progress — untouched weeks are flat, partial weeks get
// a subtle→medium gradient wash, and completed weeks get a rich gradient plus
// a glow shadow so they read as distinctly "unlocked" at a glance.
// Gradient is drawn with react-native-svg (no extra dependency).
import React, { useEffect, useRef } from "react";
import { Animated, Easing, StyleSheet, Text, View } from "react-native";
import Svg, { Defs, LinearGradient, Rect, Stop } from "react-native-svg";
import { Theme, useTheme } from "../theme";

/** Visual tier for a completion percentage. */
function tier(pct: number): "empty" | "low" | "mid" | "done" {
  if (pct >= 100) return "done";
  if (pct >= 50) return "mid";
  if (pct > 0) return "low";
  return "empty";
}

/** Gradient stops + shadow per tier. Shading intensity tracks completion. */
function looks(t: ReturnType<typeof tier>, theme: Theme) {
  const { colors, dark } = theme;
  switch (t) {
    case "done":
      return {
        stops: [colors.accent, dark ? "#C24A10" : "#9C3B0C"] as [string, string],
        stopOpacity: [1, 1] as [number, number],
        border: colors.accent,
        text: "#FFFFFF",
        sub: "rgba(255,255,255,0.85)",
        shadow: {
          shadowColor: colors.accent,
          shadowOpacity: dark ? 0.65 : 0.45,
          shadowRadius: 10,
          shadowOffset: { width: 0, height: 4 },
          elevation: 7,
        },
      };
    case "mid":
      return {
        stops: [colors.accent, colors.accent] as [string, string],
        stopOpacity: dark ? [0.55, 0.25] : ([0.4, 0.16] as [number, number]),
        border: colors.accent,
        text: colors.text,
        sub: colors.textSecondary,
        shadow: {
          shadowColor: colors.accent,
          shadowOpacity: dark ? 0.35 : 0.2,
          shadowRadius: 7,
          shadowOffset: { width: 0, height: 3 },
          elevation: 4,
        },
      };
    case "low":
      return {
        stops: [colors.accent, colors.accent] as [string, string],
        stopOpacity: dark ? [0.22, 0.06] : ([0.16, 0.04] as [number, number]),
        border: colors.border,
        text: colors.text,
        sub: colors.textTertiary,
        shadow: {
          shadowColor: dark ? "#000" : colors.text,
          shadowOpacity: dark ? 0.3 : 0.08,
          shadowRadius: 5,
          shadowOffset: { width: 0, height: 2 },
          elevation: 2,
        },
      };
    default:
      return {
        stops: [colors.backgroundElevated2, colors.backgroundElevated2] as [string, string],
        stopOpacity: [1, 1] as [number, number],
        border: colors.border,
        text: colors.textTertiary,
        sub: colors.textTertiary,
        shadow: {},
      };
  }
}

export default function WeeklyBadge({
  label,
  completed,
  target,
  pct,
  size = 64,
  current = false,
}: {
  /** Short week label, e.g. "Jul 6". */
  label: string;
  completed: number;
  target: number;
  /** 0-100 */
  pct: number;
  size?: number;
  /** The in-progress week gets a highlight ring. */
  current?: boolean;
}) {
  const theme = useTheme();
  const t = tier(pct);
  const look = looks(t, theme);
  const radius = theme.radius.lg;

  // Completed weeks pop in with a small spring — the "unlocked" moment.
  const scale = useRef(new Animated.Value(t === "done" ? 0.8 : 1)).current;
  useEffect(() => {
    if (t === "done") {
      Animated.spring(scale, { toValue: 1, useNativeDriver: true, speed: 12, bounciness: 9 }).start();
    }
  }, [t, scale]);

  // A unique gradient id per instance so multiple badges don't collide.
  const gid = useRef(`wb-${Math.random().toString(36).slice(2)}`).current;

  return (
    <Animated.View
      style={[
        {
          width: size,
          height: size,
          borderRadius: radius,
          borderWidth: current ? 2 : StyleSheet.hairlineWidth,
          borderColor: current ? theme.colors.secondary : look.border,
          backgroundColor: theme.colors.backgroundElevated,
          alignItems: "center",
          justifyContent: "center",
          overflow: "visible",
          transform: [{ scale }],
        },
        look.shadow,
      ]}
      accessibilityLabel={`Week of ${label}: ${completed} of ${target} workouts${pct >= 100 ? ", complete" : ""}`}
    >
      <View style={{ ...StyleSheet.absoluteFillObject, borderRadius: radius, overflow: "hidden" }}>
        <Svg width="100%" height="100%">
          <Defs>
            <LinearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
              <Stop offset="0" stopColor={look.stops[0]} stopOpacity={look.stopOpacity[0]} />
              <Stop offset="1" stopColor={look.stops[1]} stopOpacity={look.stopOpacity[1]} />
            </LinearGradient>
          </Defs>
          <Rect x="0" y="0" width="100%" height="100%" fill={`url(#${gid})`} />
        </Svg>
      </View>
      {t === "done" ? (
        <Text style={{ fontSize: size * 0.28, marginBottom: 1 }} maxFontSizeMultiplier={1.1}>🏆</Text>
      ) : (
        <Text
          style={{ fontSize: size * 0.24, fontWeight: "800", color: look.text }}
          maxFontSizeMultiplier={1.1}
        >
          {completed}/{target}
        </Text>
      )}
      <Text
        style={{ fontSize: size * 0.15, fontWeight: "600", color: look.sub, marginTop: 1 }}
        numberOfLines={1}
        maxFontSizeMultiplier={1.1}
      >
        {label}
      </Text>
    </Animated.View>
  );
}
