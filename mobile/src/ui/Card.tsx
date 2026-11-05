// Elevated surface container — the basic building block of every screen.
import React from "react";
import { StyleProp, StyleSheet, View, ViewStyle } from "react-native";
import { useTheme } from "../theme";

/** Rounded, bordered, shadowed container with optional left accent stripe. */
export default function Card({
  children,
  style,
  padded = true,
  accentColor,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  padded?: boolean;
  /** Optional colored left border, used to mark the "active" item in a list. */
  accentColor?: string;
}) {
  const theme = useTheme();
  return (
    <View
      style={[
        styles.base,
        {
          backgroundColor: theme.colors.backgroundElevated,
          borderRadius: theme.radius.lg,
          borderColor: theme.colors.border,
          borderWidth: theme.dark ? StyleSheet.hairlineWidth : StyleSheet.hairlineWidth,
        },
        theme.shadow.card,
        padded && { padding: theme.spacing.lg },
        accentColor ? { borderLeftWidth: 3, borderLeftColor: accentColor } : null,
        style,
      ]}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  base: { overflow: "hidden" },
});
