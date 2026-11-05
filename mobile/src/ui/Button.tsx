// Primary pressable for the app: variant palettes, three sizes, a busy
// spinner, and a subtle press-scale animation.
import React, { useRef } from "react";
import { ActivityIndicator, Animated, Pressable, StyleSheet, Text, View } from "react-native";
import { useTheme } from "../theme";

export type ButtonVariant = "primary" | "accent" | "success" | "danger" | "secondary" | "ghost";
type Size = "large" | "medium" | "small";

/** Themed button; `loading` disables it and swaps the label for a spinner. */
export default function Button({
  title,
  onPress,
  variant = "primary",
  size = "large",
  loading = false,
  disabled = false,
  icon,
  fullWidth = true,
}: {
  title: string;
  onPress: () => void;
  variant?: ButtonVariant;
  size?: Size;
  loading?: boolean;
  disabled?: boolean;
  icon?: string;
  fullWidth?: boolean;
}) {
  const theme = useTheme();
  const scale = useRef(new Animated.Value(1)).current;
  const isDisabled = disabled || loading;
  const palette = variantColors(variant, theme);

  function pressIn() {
    if (isDisabled) return;
    Animated.spring(scale, { toValue: 0.96, useNativeDriver: true, speed: 50, bounciness: 0 }).start();
  }
  function pressOut() {
    Animated.spring(scale, { toValue: 1, useNativeDriver: true, speed: 18, bounciness: 6 }).start();
  }

  return (
    <Animated.View style={[fullWidth ? styles.full : undefined, { transform: [{ scale }] }]}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ disabled: isDisabled, busy: loading }}
        onPress={onPress}
        onPressIn={pressIn}
        onPressOut={pressOut}
        disabled={isDisabled}
        style={[
          styles.base,
          size === "large" && styles.large,
          size === "medium" && styles.medium,
          size === "small" && styles.small,
          {
            backgroundColor: palette.bg,
            borderColor: palette.border ?? "transparent",
            borderWidth: palette.border ? StyleSheet.hairlineWidth : 0,
          },
          isDisabled && styles.disabled,
        ]}
      >
        {loading ? (
          <ActivityIndicator color={palette.fg} />
        ) : (
          <View style={styles.content}>
            {icon ? <Text style={[styles.icon, { color: palette.fg }]}>{icon}</Text> : null}
            <Text
              style={[styles.text, size === "small" && styles.textSmall, { color: palette.fg }]}
              numberOfLines={1}
              maxFontSizeMultiplier={1.4}
            >
              {title}
            </Text>
          </View>
        )}
      </Pressable>
    </Animated.View>
  );
}

/** Background/foreground/border palette for each visual variant. */
function variantColors(variant: ButtonVariant, theme: ReturnType<typeof useTheme>) {
  const { colors } = theme;
  switch (variant) {
    case "primary":
      return { bg: colors.text, fg: colors.background, border: null as string | null };
    case "accent":
      return { bg: colors.accent, fg: "#FFFFFF", border: null };
    case "success":
      return { bg: colors.success, fg: "#FFFFFF", border: null };
    case "danger":
      return { bg: colors.danger, fg: "#FFFFFF", border: null };
    case "ghost":
      return { bg: "transparent", fg: colors.accent, border: null };
    case "secondary":
    default:
      return { bg: "transparent", fg: colors.text, border: colors.border };
  }
}

const styles = StyleSheet.create({
  full: { width: "100%" },
  base: { borderRadius: 14, alignItems: "center", justifyContent: "center" },
  large: { paddingVertical: 16, paddingHorizontal: 20 },
  medium: { paddingVertical: 12, paddingHorizontal: 16 },
  small: { paddingVertical: 9, paddingHorizontal: 14 },
  content: { flexDirection: "row", alignItems: "center", gap: 8 },
  icon: { fontSize: 16, fontWeight: "700" },
  text: { fontSize: 16, fontWeight: "700" },
  textSmall: { fontSize: 13, fontWeight: "700" },
  disabled: { opacity: 0.4 },
});
