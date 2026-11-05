// Onboarding: capture training habits (days/week, session length, experience)
// — the three inputs the program generator needs. Server defaults pre-fill.
import React, { useEffect, useMemo, useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { UserApi } from "../api";
import { friendlyError } from "../errors";
import { Theme, useTheme } from "../theme";
import { Button, Chip, ScreenBackground } from "../ui";

const DAYS = [3, 4, 5];
const MINUTES = [30, 45, 60, 75, 90];
const EXPERIENCE: { key: string; label: string }[] = [
  { key: "beginner", label: "New to lifting — ease me in" },
  { key: "conservative", label: "Returning / cautious" },
  { key: "intermediate", label: "Intermediate" },
  { key: "advanced", label: "Advanced" },
];

/** Habit picker; saving marks onboarding complete and calls onDone(). */
export default function OnboardingScreen({ onDone }: { onDone: () => void }) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const [name, setName] = useState("");
  const [days, setDays] = useState(3);
  const [minutes, setMinutes] = useState(60);
  const [experience, setExperience] = useState("conservative");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const d = await UserApi.habitsDefaults();
        setDays(d.days_per_week);
        setMinutes(d.session_minutes);
        setExperience(d.experience);
      } catch {
        /* fall back to local defaults */
      }
    })();
  }, []);

  async function save() {
    setError(null);
    setSaving(true);
    try {
      await UserApi.setHabits({
        days_per_week: days,
        session_minutes: minutes,
        experience,
        name: name.trim() || undefined,
      });
      onDone();
    } catch (e) {
      setError(friendlyError(e, "Could not save"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <ScreenBackground>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Text style={styles.title} maxFontSizeMultiplier={1.3}>Let's set you up</Text>
        <Text style={styles.subtitle} maxFontSizeMultiplier={1.6}>This shapes the programs we build for you. You can change it anytime.</Text>

        {/* Guideline 1.4.1 — the app prescribes training loads and progression.
            This is the first-run gate every user passes through, so it carries
            the app-wide notice; the nutrition-specific one lives on
            NutritionSetupScreen. */}
        <Text style={styles.disclaimer} maxFontSizeMultiplier={1.6}>
          WeightProgram gives general fitness information, not medical advice. Check with your
          doctor before starting a new training program.
        </Text>

        <Text style={styles.label}>What should we call you?</Text>
        <TextInput
          style={styles.input}
          placeholder="First name (optional)"
          placeholderTextColor={theme.colors.textTertiary}
          autoCapitalize="words"
          autoComplete="name-given"
          textContentType="givenName"
          returnKeyType="done"
          maxLength={80}
          value={name}
          onChangeText={setName}
        />

        <Text style={styles.label}>Days per week</Text>
        <View style={styles.chipRow}>
          {DAYS.map((d) => (
            <Chip key={d} label={`${d}`} selected={d === days} onPress={() => setDays(d)} />
          ))}
        </View>

        <Text style={styles.label}>Session length (minutes)</Text>
        <View style={styles.chipRow}>
          {MINUTES.map((m) => (
            <Chip key={m} label={`${m}`} selected={m === minutes} onPress={() => setMinutes(m)} />
          ))}
        </View>

        <Text style={styles.label}>Experience</Text>
        <View style={styles.chipRow}>
          {EXPERIENCE.map((e) => (
            <Chip key={e.key} label={e.label} selected={e.key === experience} onPress={() => setExperience(e.key)} />
          ))}
        </View>
        {experience === "beginner" ? (
          <Text style={styles.hint} maxFontSizeMultiplier={1.6}>
            We'll start you with one exercise per day and add one more each week — no rush, no overwhelm.
          </Text>
        ) : null}

        {error ? <Text style={styles.error} maxFontSizeMultiplier={1.6}>{error}</Text> : null}

        <View style={{ marginTop: 28 }}>
          <Button title="Continue" onPress={save} loading={saving} disabled={saving} variant="primary" />
        </View>
      </ScrollView>
      </KeyboardAvoidingView>
    </ScreenBackground>
  );
}

function getStyles(theme: Theme) {
  return StyleSheet.create({
    container: { flexGrow: 1, justifyContent: "center", padding: 24, paddingVertical: 40 },
    title: { fontSize: 26, fontWeight: "700", color: theme.colors.text },
    subtitle: { fontSize: 14, color: theme.colors.textSecondary, marginBottom: 20, lineHeight: 19 },
    label: { fontSize: 15, fontWeight: "700", color: theme.colors.text, marginTop: 18, marginBottom: 8 },
    input: {
      borderWidth: 1, borderColor: theme.colors.border, borderRadius: 12, padding: 14,
      fontSize: 16, color: theme.colors.text, backgroundColor: theme.colors.backgroundElevated,
    },
    chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
    hint: { fontSize: 13, color: theme.colors.textSecondary, marginTop: 10, lineHeight: 18 },
    // Medical disclaimer (guideline 1.4.1) — legible, not fine print.
    disclaimer: {
      fontSize: 13,
      color: theme.colors.textSecondary,
      lineHeight: 18,
      backgroundColor: theme.colors.backgroundElevated,
      borderRadius: 12,
      padding: 12,
      marginBottom: 4,
    },
    error: { color: theme.colors.danger, marginTop: 14, fontWeight: "600" },
  });
}
