// Small pill-shaped status label (e.g. "COMPOUND", "PR", "STALE").
import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { useTheme } from "../theme";

export type BadgeTone = "neutral" | "accent" | "success" | "warning" | "danger";

/** Tinted pill label; tone picks a soft background + matching text color. */
export default function Badge({ label, tone = "neutral" }: { label: string; tone?: BadgeTone }) {
  const theme = useTheme();
  const { colors } = theme;
  const map: Record<BadgeTone, { bg: string; fg: string }> = {
    neutral: { bg: colors.backgroundElevated2, fg: colors.textSecondary },
    accent: { bg: colors.accentSoft, fg: colors.accent },
    success: { bg: colors.successSoft, fg: colors.success },
    warning: { bg: colors.warningSoft, fg: colors.warning },
    danger: { bg: colors.dangerSoft, fg: colors.danger },
  };
  const c = map[tone];
  return (
    <View style={[styles.base, { backgroundColor: c.bg, borderRadius: theme.radius.pill }]}>
      <Text style={[styles.text, { color: c.fg }]} maxFontSizeMultiplier={1.4}>
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  base: { alignSelf: "flex-start", paddingVertical: 5, paddingHorizontal: 10 },
  text: { fontSize: 12, fontWeight: "700" },
});
