// Selectable pill used for single/multi-choice option rows (diet, ranges…).
import React from "react";
import { Pressable, StyleSheet, Text } from "react-native";
import { useTheme } from "../theme";

/** Toggleable pill; selected state inverts to a solid fill. */
export default function Chip({
  label,
  selected,
  onPress,
  disabled,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
  disabled?: boolean;
}) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected, disabled }}
      disabled={disabled}
      onPress={onPress}
      style={[
        styles.base,
        {
          borderRadius: theme.radius.pill,
          borderColor: selected ? theme.colors.text : theme.colors.border,
          backgroundColor: selected ? theme.colors.text : "transparent",
        },
        disabled && styles.disabled,
      ]}
    >
      <Text
        style={[styles.text, { color: selected ? theme.colors.background : theme.colors.text, fontWeight: selected ? "700" : "500" }]}
        maxFontSizeMultiplier={1.6}
      >
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: { borderWidth: 1, paddingVertical: 10, paddingHorizontal: 16 },
  text: { fontSize: 15 },
  disabled: { opacity: 0.4 },
});
