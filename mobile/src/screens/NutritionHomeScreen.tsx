// Neutron home: today's protein ring, quick-log, weight check-in, and the
// doors into Scan My Kitchen / Recipes / Tracker / Protein Boosters.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import Svg, { Circle } from "react-native-svg";
import * as Haptics from "expo-haptics";
import { NutritionApi, NutritionSummary } from "../api";
import { quotaLabel, useBilling } from "../BillingContext";
import { Theme, useTheme } from "../theme";
import { Badge, Button, Card, ChevronGlyph, ScreenBackground, Stepper } from "../ui";

/** Big circular progress ring: today's grams vs target, color-tiered. */
function ProteinRing({ pct, grams, target, theme }: { pct: number; grams: number; target: number | null; theme: Theme }) {
  const size = 190;
  const stroke = 16;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const clamped = Math.min(1, Math.max(0, pct / 100));
  const ringColor = clamped >= 0.9 ? theme.colors.success : clamped >= 0.5 ? theme.colors.secondary : theme.colors.accent;
  return (
    <View style={{ width: size, height: size, alignItems: "center", justifyContent: "center", alignSelf: "center" }}>
      <Svg width={size} height={size} style={{ transform: [{ rotate: "-90deg" }] }}>
        <Circle cx={size / 2} cy={size / 2} r={r} stroke={theme.colors.backgroundElevated2}
          strokeWidth={stroke} fill="none" />
        <Circle cx={size / 2} cy={size / 2} r={r} stroke={ringColor} strokeWidth={stroke} fill="none"
          strokeDasharray={`${c}`} strokeDashoffset={c * (1 - clamped)} strokeLinecap="round" />
      </Svg>
      <View style={{ position: "absolute", alignItems: "center" }}>
        <Text style={{ fontSize: 36, fontWeight: "800", color: theme.colors.text }} maxFontSizeMultiplier={1.1}>
          {Math.round(grams)} g
        </Text>
        <Text style={{ ...theme.typography.subhead, color: theme.colors.textSecondary }} maxFontSizeMultiplier={1.3}>
          {target ? `of ${Math.round(target)} g · ${Math.round(pct)}%` : "set your target"}
        </Text>
      </View>
    </View>
  );
}

export default function NutritionHomeScreen({
  onBack,
  onScanKitchen,
  onRecipes,
  onTracker,
  onBoosters,
  onVoiceLog,
  onEditProfile,
}: {
  onBack: () => void;
  onScanKitchen: () => void;
  onRecipes: () => void;
  onTracker: () => void;
  onBoosters: () => void;
  onVoiceLog: () => void;
  onEditProfile: () => void;
}) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  // Meal-scan quota, displayed only — the server's 402 is the enforcement.
  const { status: billing } = useBilling();
  const [summary, setSummary] = useState<NutritionSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [quickGrams, setQuickGrams] = useState("25");
  const [logging, setLogging] = useState(false);
  const [weightInput, setWeightInput] = useState("");
  const [showWeight, setShowWeight] = useState(false);

  const load = useCallback(async () => {
    try {
      setSummary(await NutritionApi.summary());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function quickLog() {
    const grams = parseFloat(quickGrams) || 0;
    if (grams <= 0) return;
    setLogging(true);
    try {
      const res = await NutritionApi.logProtein(grams, "Quick add");
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      if (res.newly_earned_badges.length > 0) {
        Alert.alert("Badge earned! 🏅", res.newly_earned_badges.join(", ").replace(/_/g, " "));
      }
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLogging(false);
    }
  }

  /** Guard an accidental tap: confirm the amount before logging (mirrors the
   * Restart-program confirmation on ProgramScreen). */
  function confirmQuickLog() {
    const grams = parseFloat(quickGrams) || 0;
    if (grams <= 0) return;
    Alert.alert(
      "Log protein?",
      `Add ${grams} g of protein to today's total?`,
      [
        { text: "Cancel", style: "cancel" },
        { text: "Log it", onPress: quickLog },
      ],
    );
  }

  async function logWeight() {
    const kg = parseFloat(weightInput) || 0;
    if (kg <= 0) return;
    try {
      await NutritionApi.logWeight(kg);
      setShowWeight(false);
      setWeightInput("");
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const pct = summary?.today_pct ?? 0;
  // "Unlimited" on pro, a countdown otherwise; nothing at all if billing
  // status hasn't loaded, so an outage degrades quietly.
  const mealScansLeft = billing?.meal_scans_remaining;
  const mealScansLabel = quotaLabel(mealScansLeft, "meal scan");
  const mealScansTone = mealScansLeft === undefined ? "neutral"
    : mealScansLeft < 0 ? "success"
    : mealScansLeft === 0 ? "danger"
    : mealScansLeft <= 2 ? "warning" : "neutral";

  return (
    <ScreenBackground showHome={false}>
      <ScrollView contentContainerStyle={styles.container}>
        <View style={[styles.headerRow, { justifyContent: "flex-end" }]}>
          <Pressable onPress={onEditProfile} accessibilityRole="button" style={styles.editBtn}>
            <Text style={styles.editText} maxFontSizeMultiplier={1.3}>Edit profile</Text>
          </Pressable>
        </View>

        <Text style={styles.title} maxFontSizeMultiplier={1.2}>Neutron</Text>
        <Text style={styles.subtitle} maxFontSizeMultiplier={1.4}>Protein, protected.</Text>

        {loading ? (
          <ActivityIndicator size="large" color={theme.colors.text} style={{ marginTop: 60 }} />
        ) : (
          <>
            <Card style={{ gap: 14 }}>
              <ProteinRing pct={pct} grams={summary?.today_g ?? 0} target={summary?.target_g ?? null} theme={theme} />
              <Text style={styles.message} maxFontSizeMultiplier={1.4}>{summary?.message}</Text>
              <View style={styles.badgeRow}>
                {summary && summary.daily_streak > 0 ? (
                  <Badge label={`🔥 ${summary.daily_streak}-day streak`} tone="accent" />
                ) : null}
                {summary ? <Badge label={`Lv ${summary.level} · ${summary.level_title}`} tone="success" /> : null}
                {mealScansLabel ? <Badge label={mealScansLabel} tone={mealScansTone} /> : null}
              </View>
            </Card>

            <NavRow theme={theme} title="Voice Log" emoji="🎙"
              caption="Say what you ate — protein is estimated on your phone and logged in seconds."
              onPress={onVoiceLog} />

            <Card style={{ gap: 12 }}>
              <Text style={styles.sectionTitle} maxFontSizeMultiplier={1.3}>Quick log</Text>
              <Stepper label="Protein" value={quickGrams} onChange={setQuickGrams}
                step={5} min={0} max={200} suffix="g" />
              <Button title="Log protein" onPress={confirmQuickLog} loading={logging} variant="accent" />
            </Card>

            <Card style={{ gap: 10 }}>
              <Pressable onPress={() => setShowWeight((s) => !s)} accessibilityRole="button"
                style={styles.rowBetween}>
                <Text style={styles.sectionTitle} maxFontSizeMultiplier={1.3}>Weight check-in</Text>
                <ChevronGlyph color={theme.colors.textTertiary} />
              </Pressable>
              {showWeight ? (
                <>
                  <Stepper label="Today's weight" value={weightInput} onChange={setWeightInput}
                    step={0.5} min={25} max={350} suffix="kg" allowDecimal />
                  <Button title="Save weight" size="medium" variant="secondary" onPress={logWeight} />
                  <Text style={styles.hint} maxFontSizeMultiplier={1.5}>
                    Your protein target adjusts automatically as your weight changes
                    (your multiplier — default 0.69 g/lb).
                  </Text>
                </>
              ) : null}
            </Card>
            <NavRow theme={theme} title="Scan My Kitchen" emoji="📷"
              caption="Photograph your pantry, fridge or freezer — get recipes from what you own."
              onPress={onScanKitchen} />
            <NavRow theme={theme} title="Recipes & Meal Builder" emoji="🍳"
              caption="High-protein recipes, filters, and a Surprise Me full-day plan."
              onPress={onRecipes} />
            <NavRow theme={theme} title="Protein Tracker" emoji="📈"
              caption="Weekly bars, 4-week trend, streaks, badges and your muscle score."
              onPress={onTracker} />
            {/* Protein Boosters is HIDDEN for the 1.0 App Store submission.
                Every product URL is still an example.com placeholder
                (routers/nutrition.py `_MARKETPLACE`), and the screen itself
                tells the user the links aren't real — shipping that is an
                App Store 2.1 (App Completeness) rejection.
                Everything behind this row still works: the route in App.tsx,
                ProteinBoostersScreen, and GET /nutrition/marketplace are all
                intact. To re-enable once an affiliate program is live and the
                real URLs are in `_MARKETPLACE`, delete this comment and restore
                the NavRow below. That is a JS-only change — no native rebuild.

            <NavRow theme={theme} title="Protein Boosters" emoji="🛒"
              caption="Curated high-protein products that work with a small appetite."
              onPress={onBoosters} />
            */}

            {error ? <Text style={styles.error} maxFontSizeMultiplier={1.4}>{error}</Text> : null}
            <Text style={styles.privacy} maxFontSizeMultiplier={1.6}>
              Kitchen photos are processed securely and never stored — only the food list you
              confirm is saved.
            </Text>
          </>
        )}
      </ScrollView>
    </ScreenBackground>
  );
}

function NavRow({ theme, title, caption, emoji, onPress }: {
  theme: Theme; title: string; caption: string; emoji: string; onPress: () => void;
}) {
  const styles = useMemo(() => getStyles(theme), [theme]);
  return (
    <Pressable onPress={onPress} accessibilityRole="button">
      <Card style={styles.navRow}>
        <Text style={{ fontSize: 26 }}>{emoji}</Text>
        <View style={{ flex: 1, marginLeft: 12 }}>
          <Text style={styles.navTitle} maxFontSizeMultiplier={1.3}>{title}</Text>
          <Text style={styles.navCaption} maxFontSizeMultiplier={1.5}>{caption}</Text>
        </View>
        <ChevronGlyph color={theme.colors.textTertiary} />
      </Card>
    </Pressable>
  );
}

function getStyles(theme: Theme) {
  return StyleSheet.create({
    container: { padding: 20, gap: 14, paddingBottom: 40 },
    headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
    backBtn: { paddingVertical: 4 },
    backText: { ...theme.typography.headline, color: theme.colors.accent },
    editBtn: { minHeight: 44, justifyContent: "center" },
    editText: { ...theme.typography.subhead, color: theme.colors.secondary },
    title: { ...theme.typography.largeTitle, color: theme.colors.text },
    subtitle: { ...theme.typography.subhead, color: theme.colors.textSecondary, marginTop: -8 },
    sectionTitle: { ...theme.typography.headline, color: theme.colors.text },
    message: { ...theme.typography.subhead, color: theme.colors.textSecondary, textAlign: "center" },
    badgeRow: { flexDirection: "row", gap: 8, justifyContent: "center", flexWrap: "wrap" },
    rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
    hint: { ...theme.typography.footnote, color: theme.colors.textTertiary },
    navRow: { flexDirection: "row", alignItems: "center" },
    navTitle: { ...theme.typography.headline, color: theme.colors.text },
    navCaption: { ...theme.typography.footnote, color: theme.colors.textSecondary, marginTop: 2 },
    error: { ...theme.typography.subhead, color: theme.colors.danger },
    privacy: { ...theme.typography.footnote, color: theme.colors.textTertiary, textAlign: "center", marginTop: 6 },
  });
}
