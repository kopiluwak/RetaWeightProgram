// Home dashboard: greeting header, overflow menu, the gamification hero
// (level/XP, streaks, weekly challenge, protein progress, quick actions) and
// the three entry cards (Equipment, Progress, Nutrition). Loads the current
// inventory and the gamification summary in parallel.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Alert, Animated, Easing, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { AccountApi, GamificationApi, GamificationSummary, InventoryApi, InventoryVersion, Me } from "../api";
import { quotaLabel, useBilling } from "../BillingContext";
import { prettyType } from "../equipment";
import { friendlyError } from "../errors";
import { Theme, useTheme } from "../theme";
import {
  Badge,
  ChevronGlyph,
  DotsGlyph,
  DumbbellGlyph,
  GamificationHeader,
  IconBadge,
  NutritionGlyph,
  OverflowMenu,
  ScreenBackground,
  TrendGlyph,
} from "../ui";
import type { MenuItem } from "../ui";

/** Time-of-day greeting line. */
function greeting(): string {
  const h = new Date().getHours();
  if (h < 5) return "Still up";
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  if (h < 21) return "Good evening";
  return "Winding down";
}

/** Best-effort first name from the email's local part ("jo.smith" -> "Jo").
 *  Only used as a fallback when the user didn't give a name at onboarding. */
function prettyName(email: string): string {
  const local = email.split("@")[0] ?? "";
  const first = local.split(/[._-]/)[0] ?? local;
  return first ? first.charAt(0).toUpperCase() + first.slice(1) : "there";
}

/** The name to greet by: the onboarding name if given, else derived from email. */
function displayName(me: Me): string {
  const given = me.name?.trim();
  return given ? given : prettyName(me.email);
}

export default function HomeScreen({
  me,
  onScan,
  onViewProgram,
  onViewProgress,
  onNutrition,
  onSignOut,
  onAccountDeleted,
}: {
  me: Me;
  onScan: () => void;
  onViewProgram: () => void;
  onViewProgress: () => void;
  onNutrition: () => void;
  onSignOut: () => void;
  /** Called after deletion is requested; the session is already gone. */
  onAccountDeleted: () => void;
}) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  // Server-side quota, displayed only — the 402 is what actually enforces it.
  const { status: billing, showPaywall } = useBilling();
  const [inv, setInv] = useState<InventoryVersion | null>(null);
  const [gami, setGami] = useState<GamificationSummary | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    // Fetched in parallel; the hero simply doesn't render if the summary
    // fails, so a gamification outage can never block the home screen.
    const [invRes, gamiRes] = await Promise.allSettled([
      InventoryApi.current(),
      GamificationApi.summary(),
    ]);
    setInv(invRes.status === "fulfilled" ? invRes.value : null);
    setGami(gamiRes.status === "fulfilled" ? gamiRes.value : null);
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Gentle staggered entrance: header first, then the content cards — the
  // kind of tiny sequencing detail that makes a static screen feel alive.
  const headerAnim = useRef(new Animated.Value(0)).current;
  const cardsAnim = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.stagger(90, [
      Animated.timing(headerAnim, { toValue: 1, duration: 420, easing: Easing.out(Easing.cubic), useNativeDriver: true }),
      Animated.timing(cardsAnim, { toValue: 1, duration: 420, easing: Easing.out(Easing.cubic), useNativeDriver: true }),
    ]).start();
  }, [headerAnim, cardsAnim]);

  const headerStyle = {
    opacity: headerAnim,
    transform: [{ translateY: headerAnim.interpolate({ inputRange: [0, 1], outputRange: [10, 0] }) }],
  };
  const cardsStyle = {
    opacity: cardsAnim,
    transform: [{ translateY: cardsAnim.interpolate({ inputRange: [0, 1], outputRange: [16, 0] }) }],
  };

  const itemCount = inv?.items.reduce((sum, it) => sum + it.quantity, 0) ?? 0;
  const typeNames = inv?.items.map((it) => prettyType(it.type)) ?? [];
  const typePreview =
    typeNames.length > 3 ? `${typeNames.slice(0, 3).join(", ")} +${typeNames.length - 3} more` : typeNames.join(", ");

  const confirmSignOut = () =>
    Alert.alert("Sign out?", "You'll need to enter a new email code to sign back in.", [
      { text: "Cancel", style: "cancel" },
      { text: "Sign out", style: "destructive", onPress: onSignOut },
    ]);

  // Account deletion (App Store Review Guideline 5.1.1(v)). Two-step on purpose:
  // the first alert explains what goes and what is kept, the second is the point
  // of no return. Apple requires this be reachable in-app, not just by email.
  async function doRequestDeletion() {
    try {
      const res = await AccountApi.requestDeletion();
      Alert.alert("Account scheduled for deletion", res.message, [
        { text: "OK", onPress: onAccountDeleted },
      ]);
    } catch (e) {
      Alert.alert("Couldn't delete account", friendlyError(e));
    }
  }

  const confirmDeleteAccount = () =>
    Alert.alert(
      "Delete your account?",
      "This permanently deletes your account, workout history, bodyweight and " +
        "food logs, dietary preferences and any equipment photos you shared.\n\n" +
        "You have 30 days to change your mind — sign back in before then to " +
        "cancel. After that it can't be undone.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Continue",
          style: "destructive",
          onPress: () =>
            Alert.alert("Are you sure?", "This is your last chance to keep your account.", [
              { text: "Keep my account", style: "cancel" },
              { text: "Delete account", style: "destructive", onPress: doRequestDeletion },
            ]),
        },
      ],
    );

  // Remaining equipment scans, shown on the Equipment card. Hidden entirely
  // when we have no billing status yet, so a billing outage degrades to the
  // pre-monetization UI rather than to a wrong number.
  const scansLeft = billing?.equipment_scans_remaining;
  const scansLabel = quotaLabel(scansLeft, "scan");
  const scansTone = scansLeft === undefined ? "neutral"
    : scansLeft < 0 ? "success"
    : scansLeft === 0 ? "danger"
    : scansLeft <= 2 ? "warning" : "neutral";

  const menuItems: MenuItem[] = [
    { label: inv ? "Re-scan equipment" : "Scan equipment", onPress: onScan },
    ...(billing && billing.tier !== "pro"
      ? [{ label: "Unlock more scans", onPress: () => showPaywall() }]
      : []),
    ...(inv ? [{ label: "View / build program", onPress: onViewProgram }] : []),
    { label: "Progress & history", onPress: onViewProgress },
    { label: "Nutrition (Neutron)", onPress: onNutrition },
    { label: "Sign out", onPress: confirmSignOut, destructive: true },
    { label: "Delete account", onPress: confirmDeleteAccount, destructive: true },
  ];

  return (
    <ScreenBackground showHome={false}>
      <ScrollView contentContainerStyle={styles.container}>
        <Animated.View style={[styles.headerRow, headerStyle]}>
          <View style={{ flex: 1 }}>
            <Text style={styles.greeting} maxFontSizeMultiplier={1.2} numberOfLines={1}>
              {greeting()}
            </Text>
            <Text style={styles.name} maxFontSizeMultiplier={1.2} numberOfLines={1}>
              {displayName(me)}
            </Text>
          </View>

          <OverflowMenu
            items={menuItems}
            trigger={(open, isOpen) => (
              <MenuTrigger onPress={open} active={isOpen} theme={theme} />
            )}
          />
        </Animated.View>

        <Animated.View style={[{ gap: 18 }, cardsStyle]}>
          {gami && (
            <GamificationHeader
              summary={gami}
              onLogWorkout={onViewProgram}
              onLogProtein={onNutrition}
              onViewChallenge={onViewProgress}
            />
          )}

          <HomeCard
            theme={theme}
            icon={<DumbbellGlyph color="#FFFFFF" />}
            iconTint={theme.colors.accent}
            title="Equipment"
            onPress={() => (inv ? onViewProgram() : onScan())}
            trailing={scansLabel ? <Badge label={scansLabel} tone={scansTone} /> : undefined}
          >
            {loading ? (
              <ActivityIndicator color={theme.colors.text} style={{ marginTop: 6, alignSelf: "flex-start" }} />
            ) : inv && inv.items.length > 0 ? (
              <>
                <Text style={styles.cardHeadline} maxFontSizeMultiplier={1.4}>
                  {itemCount} piece{itemCount === 1 ? "" : "s"} of equipment
                </Text>
                <Text style={styles.cardCaption} numberOfLines={1} maxFontSizeMultiplier={1.6}>
                  {typePreview}
                </Text>
              </>
            ) : (
              <>
                <Text style={styles.cardHeadline} maxFontSizeMultiplier={1.4}>No equipment yet</Text>
                <Text style={[styles.cardCaption, { color: theme.colors.accent }]} maxFontSizeMultiplier={1.6}>
                  Tap to scan your setup
                </Text>
              </>
            )}
          </HomeCard>

          <HomeCard
            theme={theme}
            icon={<TrendGlyph color="#FFFFFF" />}
            iconTint={theme.colors.success}
            title="Progress"
            onPress={onViewProgress}
          >
            <Text style={styles.cardHeadline} maxFontSizeMultiplier={1.4}>Trends, PRs and history</Text>
            <Text style={styles.cardCaption} maxFontSizeMultiplier={1.6}>
              See what all that logging is buying you.
            </Text>
          </HomeCard>

          <HomeCard
            theme={theme}
            icon={<NutritionGlyph color="#FFFFFF" />}
            iconTint={theme.colors.secondary}
            title="Nutrition"
            onPress={onNutrition}
          >
            <Text style={styles.cardHeadline} maxFontSizeMultiplier={1.4}>Neutron — protein, protected</Text>
            <Text style={styles.cardCaption} maxFontSizeMultiplier={1.6}>
              Scan your kitchen, hit your protein target, keep your muscle.
            </Text>
          </HomeCard>
        </Animated.View>
      </ScrollView>
    </ScreenBackground>
  );
}

/** Round three-dot button that opens the overflow menu (press-scale feedback). */
function MenuTrigger({ onPress, active, theme }: { onPress: () => void; active: boolean; theme: Theme }) {
  const scale = useRef(new Animated.Value(1)).current;
  return (
    <Animated.View style={{ transform: [{ scale }] }}>
      <Pressable
        accessibilityLabel="More options"
        accessibilityRole="button"
        onPressIn={() => Animated.spring(scale, { toValue: 0.9, useNativeDriver: true, speed: 50 }).start()}
        onPressOut={() => Animated.spring(scale, { toValue: 1, useNativeDriver: true, speed: 18, bounciness: 6 }).start()}
        onPress={onPress}
        style={[
          triggerStyles.btn,
          { backgroundColor: active ? theme.colors.backgroundElevated2 : "transparent", borderColor: theme.colors.border },
        ]}
      >
        <DotsGlyph color={theme.colors.text} />
      </Pressable>
    </Animated.View>
  );
}

/** Large pressable entry card: icon badge + title row + caller content. */
function HomeCard({
  theme,
  icon,
  iconTint,
  title,
  onPress,
  trailing,
  children,
}: {
  theme: Theme;
  icon: React.ReactNode;
  iconTint: string;
  title: string;
  onPress: () => void;
  trailing?: React.ReactNode;
  children: React.ReactNode;
}) {
  const scale = useRef(new Animated.Value(1)).current;
  const styles = useMemo(() => getStyles(theme), [theme]);
  return (
    <Animated.View style={{ transform: [{ scale }] }}>
      <Pressable
        onPress={onPress}
        onPressIn={() => Animated.spring(scale, { toValue: 0.98, useNativeDriver: true, speed: 50 }).start()}
        onPressOut={() => Animated.spring(scale, { toValue: 1, useNativeDriver: true, speed: 18, bounciness: 6 }).start()}
        style={[
          styles.card,
          { backgroundColor: theme.colors.backgroundElevated, borderColor: theme.colors.border },
          theme.shadow.card,
        ]}
      >
        <IconBadge tint={iconTint} size={58}>{icon}</IconBadge>
        <View style={{ flex: 1, marginLeft: 16 }}>
          <View style={styles.cardTitleRow}>
            <Text style={styles.cardTitle} maxFontSizeMultiplier={1.3}>{title}</Text>
            {trailing ?? <ChevronGlyph color={theme.colors.textTertiary} />}
          </View>
          {children}
        </View>
      </Pressable>
    </Animated.View>
  );
}

const triggerStyles = StyleSheet.create({
  btn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: StyleSheet.hairlineWidth,
  },
});

function getStyles(theme: Theme) {
  return StyleSheet.create({
    // No vertical centering any more — the gamification hero makes the page
    // tall enough that a top-anchored scroll reads better.
    container: { padding: 20, paddingTop: 4, paddingBottom: 32, flexGrow: 1, gap: 22 },
    headerRow: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between" },
    greeting: { fontSize: 34, fontWeight: "800", color: theme.colors.text, letterSpacing: -0.5 },
    name: { fontSize: 24, fontWeight: "700", color: theme.colors.accent, marginTop: 2 },
    card: {
      flexDirection: "row",
      alignItems: "center",
      padding: 22,
      borderRadius: theme.radius.xl,
      borderWidth: StyleSheet.hairlineWidth,
    },
    cardTitleRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
    cardTitle: { fontSize: 19, fontWeight: "700", color: theme.colors.text },
    cardHeadline: { fontSize: 17, fontWeight: "600", color: theme.colors.text, marginTop: 7 },
    cardCaption: { fontSize: 14, color: theme.colors.textSecondary, marginTop: 3 },
  });
}
