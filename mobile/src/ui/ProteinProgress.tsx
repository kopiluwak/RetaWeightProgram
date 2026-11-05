// Prominent animated protein progress bar (gamified daily target).
// Big grams readout, gradient fill that animates toward today's total, a
// celebratory state at >= 100%, and an optional weekly-average line. Used as
// the Protein Tracker hero and (compact) inside the home GamificationHeader.
import React, { useEffect, useRef } from "react";
import { Animated, Easing, StyleSheet, Text, View } from "react-native";
import Svg, { Defs, LinearGradient, Rect, Stop } from "react-native-svg";
import { Theme, useTheme } from "../theme";

export default function ProteinProgress({
  grams,
  targetG,
  weekAvgG,
  xpHint,
  compact = false,
}: {
  grams: number;
  targetG: number | null;
  /** Shown as a secondary line when provided. */
  weekAvgG?: number;
  /** e.g. "+25 XP" — the reward for hitting today's target. */
  xpHint?: string;
  compact?: boolean;
}) {
  const theme = useTheme();
  const styles = getStyles(theme, compact);
  const ratio = targetG && targetG > 0 ? grams / targetG : 0;
  const hit = targetG != null && targetG > 0 && grams >= targetG;

  const anim = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.timing(anim, {
      toValue: Math.max(0, Math.min(1, ratio)),
      duration: 850,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false, // animating width
    }).start();
  }, [ratio, anim]);

  // Gentle pulse on the check chip once the target is hit.
  const pulse = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    if (!hit) return;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1.12, duration: 650, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 1, duration: 650, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [hit, pulse]);

  const width = anim.interpolate({ inputRange: [0, 1], outputRange: ["0%", "100%"] });
  const barHeight = compact ? 10 : 16;
  const gid = useRef(`pp-${Math.random().toString(36).slice(2)}`).current;
  const fillColors: [string, string] = hit
    ? [theme.colors.success, theme.colors.secondary]
    : [theme.colors.secondary, theme.colors.accent];

  return (
    <View>
      <View style={styles.topRow}>
        <Text style={styles.grams} maxFontSizeMultiplier={1.2}>
          {Math.round(grams)}
          <Text style={styles.gramsUnit}>
            {targetG ? ` / ${Math.round(targetG)} g` : " g"}
          </Text>
        </Text>
        {hit ? (
          <Animated.View style={[styles.hitChip, { transform: [{ scale: pulse }] }]}>
            <Text style={styles.hitChipText} maxFontSizeMultiplier={1.2}>✓ target hit!</Text>
          </Animated.View>
        ) : xpHint && targetG ? (
          <View style={styles.xpChip}>
            <Text style={styles.xpChipText} maxFontSizeMultiplier={1.2}>{xpHint}</Text>
          </View>
        ) : null}
      </View>

      <View style={[styles.track, { height: barHeight, borderRadius: barHeight / 2 }]}>
        <Animated.View style={{ width, height: barHeight, borderRadius: barHeight / 2, overflow: "hidden" }}>
          <Svg width="100%" height="100%">
            <Defs>
              <LinearGradient id={gid} x1="0" y1="0" x2="1" y2="0">
                <Stop offset="0" stopColor={fillColors[0]} />
                <Stop offset="1" stopColor={fillColors[1]} />
              </LinearGradient>
            </Defs>
            <Rect x="0" y="0" width="100%" height="100%" fill={`url(#${gid})`} />
          </Svg>
        </Animated.View>
      </View>

      {!compact && (
        <Text style={styles.subline} maxFontSizeMultiplier={1.5}>
          {targetG
            ? `${Math.max(0, Math.round(targetG - grams))} g to go today` +
              (weekAvgG != null ? ` · weekly average ${Math.round(weekAvgG)} g/day` : "")
            : "Set your weight to get a daily protein target."}
        </Text>
      )}
    </View>
  );
}

function getStyles(theme: Theme, compact: boolean) {
  return StyleSheet.create({
    topRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 7 },
    grams: {
      fontSize: compact ? 17 : 28,
      fontWeight: "800",
      color: theme.colors.text,
      letterSpacing: -0.4,
    },
    gramsUnit: { fontSize: compact ? 13 : 16, fontWeight: "600", color: theme.colors.textSecondary },
    track: { backgroundColor: theme.colors.backgroundElevated2, overflow: "hidden" },
    subline: { ...theme.typography.footnote, color: theme.colors.textTertiary, marginTop: 7 },
    hitChip: {
      backgroundColor: theme.colors.successSoft,
      borderRadius: theme.radius.pill,
      paddingHorizontal: 10,
      paddingVertical: 4,
    },
    hitChipText: { fontSize: 12, fontWeight: "800", color: theme.colors.success },
    xpChip: {
      backgroundColor: theme.colors.secondarySoft,
      borderRadius: theme.radius.pill,
      paddingHorizontal: 10,
      paddingVertical: 4,
    },
    xpChipText: { fontSize: 12, fontWeight: "800", color: theme.colors.secondary },
  });
}
