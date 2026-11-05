// Weekly challenge card: sessions-completed ring, XP stakes, and microcopy.
// Shown at the top of the Program screen so picking a workout feels like
// advancing the week's quest rather than browsing a list.
import React, { useMemo, useRef } from "react";
import { StyleSheet, Text, View } from "react-native";
import Svg, { Defs, LinearGradient, Rect, Stop } from "react-native-svg";
import type { GamificationSummary } from "../api";
import { Theme, useTheme } from "../theme";
import ProgressRing from "./ProgressRing";

export default function WeeklyChallengeCard({ summary }: { summary: GamificationSummary }) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const { workout, xp } = summary;
  const done = workout.sessions_this_week >= workout.target_per_week;
  const remaining = Math.max(0, workout.target_per_week - workout.sessions_this_week);
  const gid = useRef(`wc-${Math.random().toString(36).slice(2)}`).current;

  return (
    <View style={[styles.card, theme.shadow.card, done && styles.cardDone]}>
      <View style={styles.gradientFill}>
        <Svg width="100%" height="100%">
          <Defs>
            <LinearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
              <Stop
                offset="0"
                stopColor={done ? theme.colors.success : theme.colors.secondary}
                stopOpacity={theme.dark ? 0.22 : 0.1}
              />
              <Stop offset="1" stopColor={theme.colors.backgroundElevated} stopOpacity={1} />
            </LinearGradient>
          </Defs>
          <Rect x="0" y="0" width="100%" height="100%" fill={`url(#${gid})`} />
        </Svg>
      </View>

      <ProgressRing
        progress={workout.week_pct / 100}
        size={64}
        strokeWidth={7}
        color={done ? theme.colors.success : theme.colors.secondary}
      >
        <Text style={styles.ringText} maxFontSizeMultiplier={1.1}>
          {workout.sessions_this_week}/{workout.target_per_week}
        </Text>
      </ProgressRing>

      <View style={{ flex: 1, marginLeft: 14 }}>
        <Text style={styles.title} maxFontSizeMultiplier={1.3}>
          {done ? "Weekly challenge complete! 🏆" : "Weekly challenge"}
        </Text>
        <Text style={styles.msg} numberOfLines={2} maxFontSizeMultiplier={1.5}>
          {done
            ? `Full week banked — +${xp.per_full_week} XP bonus earned.`
            : `${remaining} session${remaining === 1 ? "" : "s"} to go · +${xp.per_workout} XP each · +${xp.per_full_week} XP week bonus`}
        </Text>
        <Text style={styles.streak} maxFontSizeMultiplier={1.5}>
          🔥 {workout.current_streak}-day streak · best {workout.longest_streak}
        </Text>
      </View>
    </View>
  );
}

function getStyles(theme: Theme) {
  return StyleSheet.create({
    card: {
      flexDirection: "row",
      alignItems: "center",
      borderRadius: theme.radius.xl,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.colors.border,
      backgroundColor: theme.colors.backgroundElevated,
      padding: 16,
      overflow: "hidden",
      marginTop: 10,
    },
    cardDone: { borderColor: theme.colors.success },
    gradientFill: { ...StyleSheet.absoluteFillObject },
    ringText: { fontSize: 14, fontWeight: "800", color: theme.colors.text },
    title: { fontSize: 16, fontWeight: "800", color: theme.colors.text },
    msg: { ...theme.typography.footnote, color: theme.colors.textSecondary, marginTop: 3 },
    streak: { ...theme.typography.footnote, color: theme.colors.textTertiary, marginTop: 3 },
  });
}
