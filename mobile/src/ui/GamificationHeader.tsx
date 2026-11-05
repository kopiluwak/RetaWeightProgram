// Home-screen hero: level + XP ring, workout streak, this week's challenge
// ring, the animated protein bar, and quick actions. Designed to be the first
// and most motivating thing the user sees (gamification spec, item 3).
import React, { useMemo, useRef } from "react";
import { Animated, Pressable, StyleSheet, Text, View } from "react-native";
import Svg, { Defs, LinearGradient, Rect, Stop } from "react-native-svg";
import type { GamificationSummary } from "../api";
import { Theme, useTheme } from "../theme";
import ProgressRing from "./ProgressRing";
import ProteinProgress from "./ProteinProgress";

export default function GamificationHeader({
  summary,
  onLogWorkout,
  onLogProtein,
  onViewChallenge,
}: {
  summary: GamificationSummary;
  onLogWorkout: () => void;
  onLogProtein: () => void;
  onViewChallenge: () => void;
}) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const { xp, workout, protein } = summary;
  const gid = useRef(`gh-${Math.random().toString(36).slice(2)}`).current;

  const levelProgress = xp.level_span > 0 ? xp.xp_into_level / xp.level_span : 1;
  const weekDone = workout.sessions_this_week >= workout.target_per_week;
  const newNames = summary.newly_earned
    .map((k) => summary.achievements.find((a) => a.key === k)?.name)
    .filter((n): n is string => !!n);

  return (
    <View style={[styles.hero, theme.shadow.card]}>
      {/* Gradient wash behind everything */}
      <View style={styles.gradientFill}>
        <Svg width="100%" height="100%">
          <Defs>
            <LinearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
              <Stop offset="0" stopColor={theme.colors.accent} stopOpacity={theme.dark ? 0.28 : 0.14} />
              <Stop offset="0.55" stopColor={theme.colors.backgroundElevated} stopOpacity={1} />
              <Stop offset="1" stopColor={theme.colors.secondary} stopOpacity={theme.dark ? 0.16 : 0.08} />
            </LinearGradient>
          </Defs>
          <Rect x="0" y="0" width="100%" height="100%" fill={`url(#${gid})`} />
        </Svg>
      </View>

      {/* Level + XP + streak */}
      <View style={styles.topRow}>
        <ProgressRing progress={levelProgress} size={78} strokeWidth={8} color={theme.colors.accent}>
          <Text style={styles.ringLevel} maxFontSizeMultiplier={1.1}>LV</Text>
          <Text style={styles.ringLevelNum} maxFontSizeMultiplier={1.1}>{xp.level}</Text>
        </ProgressRing>
        <View style={{ flex: 1, marginLeft: 14 }}>
          <Text style={styles.levelTitle} maxFontSizeMultiplier={1.2}>{xp.level_title}</Text>
          <Text style={styles.xpTotal} maxFontSizeMultiplier={1.3}>
            {xp.total.toLocaleString()} XP
          </Text>
          <Text style={styles.xpNext} maxFontSizeMultiplier={1.5}>
            {xp.level_span - xp.xp_into_level} XP to level {xp.level + 1}
          </Text>
        </View>
        <View style={styles.streakPill}>
          <Text style={styles.streakFlame} maxFontSizeMultiplier={1.1}>🔥</Text>
          <Text style={styles.streakNum} maxFontSizeMultiplier={1.1}>{workout.current_streak}</Text>
          <Text style={styles.streakSub} maxFontSizeMultiplier={1.3}>
            day{workout.current_streak === 1 ? "" : "s"} · best {workout.longest_streak}
          </Text>
        </View>
      </View>

      {/* Achievement unlocked banner */}
      {newNames.length > 0 && (
        <View style={styles.unlockBanner}>
          <Text style={styles.unlockText} maxFontSizeMultiplier={1.3} numberOfLines={2}>
            🏆 Unlocked: {newNames.join(" · ")}
          </Text>
        </View>
      )}

      {/* This week's challenge */}
      <Pressable onPress={onViewChallenge} style={styles.challengeRow} accessibilityRole="button">
        <ProgressRing
          progress={workout.week_pct / 100}
          size={54}
          strokeWidth={6}
          color={weekDone ? theme.colors.success : theme.colors.secondary}
        >
          <Text style={styles.challengeRingText} maxFontSizeMultiplier={1.1}>
            {workout.sessions_this_week}/{workout.target_per_week}
          </Text>
        </ProgressRing>
        <View style={{ flex: 1, marginLeft: 12 }}>
          <Text style={styles.challengeTitle} maxFontSizeMultiplier={1.3}>
            {weekDone ? "Week complete! 🎉" : "This week's challenge"}
          </Text>
          <Text style={styles.challengeMsg} numberOfLines={2} maxFontSizeMultiplier={1.5}>
            {summary.message}
          </Text>
        </View>
      </Pressable>

      {/* Protein */}
      <View style={{ marginTop: 12 }}>
        <ProteinProgress
          grams={protein.today_g}
          targetG={protein.target_g}
          xpHint={`+${xp.per_protein_day} XP`}
          compact
        />
        <Text style={styles.proteinSub} maxFontSizeMultiplier={1.5}>
          Protein today · {protein.week_hit_days} target day{protein.week_hit_days === 1 ? "" : "s"} this week ·
          avg {Math.round(protein.week_avg_g)} g/day
        </Text>
      </View>

      {/* Quick actions */}
      <View style={styles.actionsRow}>
        <QuickAction label="Log Workout" emoji="🏋️" onPress={onLogWorkout} theme={theme} primary />
        <QuickAction label="Log Protein" emoji="🥩" onPress={onLogProtein} theme={theme} />
        <QuickAction label="Challenge" emoji="🎯" onPress={onViewChallenge} theme={theme} />
      </View>
    </View>
  );
}

/** Small press-scale pill button for the hero's quick actions. */
function QuickAction({
  label,
  emoji,
  onPress,
  theme,
  primary = false,
}: {
  label: string;
  emoji: string;
  onPress: () => void;
  theme: Theme;
  primary?: boolean;
}) {
  const scale = useRef(new Animated.Value(1)).current;
  return (
    <Animated.View style={{ flex: 1, transform: [{ scale }] }}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={label}
        onPressIn={() => Animated.spring(scale, { toValue: 0.94, useNativeDriver: true, speed: 50 }).start()}
        onPressOut={() => Animated.spring(scale, { toValue: 1, useNativeDriver: true, speed: 18, bounciness: 8 }).start()}
        onPress={onPress}
        style={{
          alignItems: "center",
          paddingVertical: 10,
          paddingHorizontal: 4,
          borderRadius: theme.radius.lg,
          backgroundColor: primary ? theme.colors.accent : theme.colors.backgroundElevated2,
          borderWidth: StyleSheet.hairlineWidth,
          borderColor: primary ? theme.colors.accent : theme.colors.border,
        }}
      >
        <Text style={{ fontSize: 18 }} maxFontSizeMultiplier={1.1}>{emoji}</Text>
        <Text
          style={{
            fontSize: 12,
            fontWeight: "700",
            marginTop: 3,
            color: primary ? "#FFFFFF" : theme.colors.text,
          }}
          numberOfLines={1}
          maxFontSizeMultiplier={1.2}
        >
          {label}
        </Text>
      </Pressable>
    </Animated.View>
  );
}

function getStyles(theme: Theme) {
  return StyleSheet.create({
    hero: {
      borderRadius: theme.radius.xl,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.colors.border,
      backgroundColor: theme.colors.backgroundElevated,
      padding: 18,
      overflow: "hidden",
    },
    gradientFill: { ...StyleSheet.absoluteFillObject },
    topRow: { flexDirection: "row", alignItems: "center" },
    ringLevel: { fontSize: 11, fontWeight: "800", color: theme.colors.textTertiary, letterSpacing: 1 },
    ringLevelNum: { fontSize: 24, fontWeight: "800", color: theme.colors.text, marginTop: -2 },
    levelTitle: { fontSize: 19, fontWeight: "800", color: theme.colors.text, letterSpacing: -0.3 },
    xpTotal: { fontSize: 15, fontWeight: "700", color: theme.colors.accent, marginTop: 1 },
    xpNext: { ...theme.typography.footnote, color: theme.colors.textTertiary, marginTop: 1 },
    streakPill: {
      alignItems: "center",
      backgroundColor: theme.colors.backgroundElevated2,
      borderRadius: theme.radius.lg,
      paddingVertical: 8,
      paddingHorizontal: 10,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.colors.border,
    },
    streakFlame: { fontSize: 16 },
    streakNum: { fontSize: 18, fontWeight: "800", color: theme.colors.text, marginTop: -1 },
    streakSub: { fontSize: 9, fontWeight: "600", color: theme.colors.textTertiary, marginTop: 1 },
    unlockBanner: {
      marginTop: 12,
      backgroundColor: theme.colors.warningSoft,
      borderRadius: theme.radius.md,
      paddingVertical: 8,
      paddingHorizontal: 12,
    },
    unlockText: { fontSize: 13, fontWeight: "700", color: theme.colors.warning },
    challengeRow: { flexDirection: "row", alignItems: "center", marginTop: 14 },
    challengeRingText: { fontSize: 13, fontWeight: "800", color: theme.colors.text },
    challengeTitle: { fontSize: 15, fontWeight: "700", color: theme.colors.text },
    challengeMsg: { ...theme.typography.footnote, color: theme.colors.textSecondary, marginTop: 2 },
    proteinSub: { ...theme.typography.footnote, color: theme.colors.textTertiary, marginTop: 6 },
    actionsRow: { flexDirection: "row", gap: 8, marginTop: 14 },
  });
}
