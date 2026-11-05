import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
// RN core's SafeAreaView is deprecated as of RN 0.81 — this is the official
// replacement. Requires <SafeAreaProvider> at the root (see App.tsx).
import { SafeAreaView } from "react-native-safe-area-context";
import { useTheme } from "../theme";
import { useNav } from "../NavContext";

/**
 * Full-bleed backdrop shared by every screen.
 *
 * Also renders a persistent Home control (top-right) whenever a NavContext is
 * available — i.e. on every authenticated in-app screen. Pass `showHome={false}`
 * on the Home screen itself (and anywhere a Home button would be redundant).
 *
 * When `onBack` is supplied it renders a standardized top-left "‹ Back" control
 * so every sub-screen uses the same affordance in the same place (usability
 * review, navigation-consistency finding) instead of ad-hoc bottom buttons.
 *
 * NOTE: this previously rendered a Skia <Canvas> gradient here. That caused a
 * blank white screen on-device (iPhone 16 / iOS 26) — most likely the Skia
 * native view failing to draw under this build, since it was never verified
 * outside of a type-check (this sandbox has no simulator/device and no
 * network to test native builds). Reverted to a guaranteed-safe flat fill
 * using the same gunmetal theme color so the app works again.
 */
export default function ScreenBackground({
  children,
  showHome = true,
  onBack,
  backLabel = "Back",
}: {
  children: React.ReactNode;
  showHome?: boolean;
  /** When set, shows a standardized top-left back control. */
  onBack?: () => void;
  backLabel?: string;
}) {
  const theme = useTheme();
  const nav = useNav();
  return (
    <View style={[styles.fill, { backgroundColor: theme.colors.background }]}>
      <SafeAreaView style={styles.fill}>
        {onBack ? (
          // A real header row (not an overlay) so it never sits on top of a
          // screen's title — content flows below it naturally.
          <View style={styles.headerBar}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={backLabel}
              onPress={onBack}
              hitSlop={8}
              style={[
                styles.backPill,
                { backgroundColor: theme.colors.backgroundElevated2, borderColor: theme.colors.border },
              ]}
            >
              <Text style={[styles.homeText, { color: theme.colors.text }]} maxFontSizeMultiplier={1.3}>
                {`‹ ${backLabel}`}
              </Text>
            </Pressable>
          </View>
        ) : null}
        {children}
        {nav && showHome ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Go home"
            onPress={nav.goHome}
            hitSlop={8}
            style={[
              styles.homePill,
              { backgroundColor: theme.colors.backgroundElevated2, borderColor: theme.colors.border },
            ]}
          >
            <Text style={[styles.homeText, { color: theme.colors.text }]} maxFontSizeMultiplier={1.3}>
              ⌂ Home
            </Text>
          </Pressable>
        ) : null}
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  homePill: {
    position: "absolute",
    top: 6,
    right: 12,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 16,
    borderWidth: StyleSheet.hairlineWidth,
    zIndex: 50,
  },
  headerBar: {
    flexDirection: "row",
    alignItems: "center",
    minHeight: 44,
    paddingHorizontal: 12,
    paddingTop: 6,
  },
  backPill: {
    alignSelf: "flex-start",
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 16,
    borderWidth: StyleSheet.hairlineWidth,
  },
  homeText: { fontSize: 13, fontWeight: "700" },
});
