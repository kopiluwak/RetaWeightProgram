// Persistent bottom tab bar for the four top-level destinations. Replaces the
// hub-and-spoke model where every section had to be reached via Home (usability
// review, navigation finding). Shown only on top-level screens; focused flows
// (capture, workout, sub-screens) hide it and use a back control instead.
import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "../theme";
import { DumbbellGlyph, HomeGlyph, NutritionGlyph, TrendGlyph } from "./Glyphs";

export type TabKey = "home" | "program" | "progress" | "nutrition";

const TABS: { key: TabKey; label: string; Glyph: (p: { color: string }) => React.ReactElement }[] = [
  { key: "home", label: "Home", Glyph: HomeGlyph },
  { key: "program", label: "Program", Glyph: DumbbellGlyph },
  { key: "progress", label: "Progress", Glyph: TrendGlyph },
  { key: "nutrition", label: "Nutrition", Glyph: NutritionGlyph },
];

/** Bottom nav; `current` highlights the active tab, `onSelect` switches screen. */
export default function TabBar({
  current,
  onSelect,
}: {
  current: TabKey;
  onSelect: (key: TabKey) => void;
}) {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  return (
    <View
      style={[
        styles.bar,
        {
          backgroundColor: theme.colors.backgroundElevated,
          borderTopColor: theme.colors.border,
          paddingBottom: Math.max(insets.bottom, 8),
        },
      ]}
    >
      {TABS.map(({ key, label, Glyph }) => {
        const active = key === current;
        const color = active ? theme.colors.accent : theme.colors.textTertiary;
        return (
          <Pressable
            key={key}
            accessibilityRole="button"
            accessibilityState={{ selected: active }}
            accessibilityLabel={label}
            onPress={() => onSelect(key)}
            style={styles.tab}
            hitSlop={4}
          >
            <Glyph color={color} />
            <Text style={[styles.label, { color }]} maxFontSizeMultiplier={1.3} numberOfLines={1}>
              {label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: "row",
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingTop: 8,
  },
  tab: { flex: 1, alignItems: "center", justifyContent: "center", gap: 4, minHeight: 44 },
  label: { fontSize: 11, fontWeight: "700" },
});
