// Neutron: protein profile setup / editor.
// First use: weight (kg) + optional goal weight -> 1 g/kg daily protein target.
// Later: same screen edits everything, including a custom target override,
// diet pattern, and hard dietary restrictions (saved permanently, applied to
// every recipe generation).
import React, { useEffect, useMemo, useState } from "react";
import { ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { NutritionApi, NutritionProfile } from "../api";
import { Theme, useTheme } from "../theme";
import { Button, Card, Chip, ScreenBackground, Stepper } from "../ui";

const DIET_PATTERNS: { key: string; label: string }[] = [
  { key: "omnivore", label: "Omnivore" },
  { key: "vegetarian", label: "Vegetarian" },
  { key: "pescatarian", label: "Pescatarian" },
  { key: "vegan", label: "Vegan" },
];

// Auto-target multiplier presets (g protein per kg bodyweight).
// Default is 1.52 g/kg ≈ 0.69 g/lb; 2.2 ≈ the classic 1 g per lb.
// Preset labels are deliberately NON-CLINICAL: "GLP-1 minimum" read as a
// medical threshold this app is in no position to define (guideline 1.4.1).
const DEFAULT_MULTIPLIER = 1.52;
const MULTIPLIERS: { value: number; label: string; note: string }[] = [
  { value: 1.0, label: "1.0 g/kg", note: "lower" },
  { value: DEFAULT_MULTIPLIER, label: "1.52 g/kg", note: "≈ 0.69 g/lb · default" },
  { value: 2.2, label: "2.2 g/kg", note: "≈ 1 g per lb" },
];

const RESTRICTIONS: { key: string; label: string }[] = [
  { key: "no_red_meat", label: "No red meat (Alpha-Gal)" },
  { key: "no_dairy", label: "No dairy" },
  { key: "no_garlic", label: "No garlic" },
  { key: "no_onion", label: "No onion" },
  { key: "keto", label: "Keto" },
  { key: "low_carb", label: "Low-carb" },
];

export default function NutritionSetupScreen({
  firstRun,
  onDone,
  onBack,
}: {
  firstRun: boolean;
  onDone: (profile: NutritionProfile) => void;
  onBack?: () => void;
}) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const [loading, setLoading] = useState(!firstRun);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [weight, setWeight] = useState("");
  const [goal, setGoal] = useState("");
  const [customTarget, setCustomTarget] = useState(""); // empty = auto (multiplier × kg)
  const [multiplier, setMultiplier] = useState(DEFAULT_MULTIPLIER);
  const [diet, setDiet] = useState("omnivore");
  const [restrictions, setRestrictions] = useState<string[]>([]);
  const [customInput, setCustomInput] = useState("");

  useEffect(() => {
    if (firstRun) return;
    NutritionApi.profile()
      .then((p) => {
        setWeight(p.current_weight_kg != null ? String(p.current_weight_kg) : "");
        setGoal(p.goal_weight_kg != null ? String(p.goal_weight_kg) : "");
        setCustomTarget(p.target_mode === "custom" && p.protein_target_g != null ? String(p.protein_target_g) : "");
        setMultiplier(p.protein_multiplier || DEFAULT_MULTIPLIER);
        setDiet(p.diet_pattern);
        setRestrictions(p.restrictions);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [firstRun]);

  const weightNum = parseFloat(weight) || 0;
  const autoTarget = weightNum > 0 ? Math.round(weightNum * multiplier * 10) / 10 : null;
  const effectiveTarget = customTarget ? parseFloat(customTarget) || null : autoTarget;

  function toggleRestriction(key: string) {
    setRestrictions((prev) => (prev.includes(key) ? prev.filter((r) => r !== key) : [...prev, key]));
  }

  function addCustom() {
    const v = customInput.trim().toLowerCase();
    if (!v) return;
    const key = `custom:${v}`;
    if (!restrictions.includes(key)) setRestrictions((prev) => [...prev, key]);
    setCustomInput("");
  }

  async function save() {
    if (!weightNum) {
      setError("Enter your current weight so we can set your protein target.");
      return;
    }
    setError(null);
    setSaving(true);
    try {
      const p = await NutritionApi.saveProfile({
        current_weight_kg: weightNum,
        goal_weight_kg: parseFloat(goal) || null,
        protein_target_g: customTarget ? parseFloat(customTarget) || null : null,
        protein_multiplier: multiplier,
        diet_pattern: diet,
        restrictions,
      });
      onDone(p);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <ScreenBackground>
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Text style={styles.title} maxFontSizeMultiplier={1.2}>
          {firstRun ? "Your protein target" : "Protein profile"}
        </Text>
        <Text style={styles.subtitle} maxFontSizeMultiplier={1.4}>
          On GLP-1 medication, appetite drops but your muscles' protein needs don't. We default
          to 0.69 g of protein per lb of body weight (1.52 g/kg) daily to help preserve lean mass
          while losing weight — 1 g/kg is a commonly cited floor.
        </Text>

        {/* App Store Review Guideline 1.4.1 (Safety — Physical Harm). This screen
            frames the app around prescription GLP-1 medication AND derives a
            numeric intake target from body weight, so Apple's "remind users to
            check with a doctor" expectation applies squarely. Persistent text,
            not a dismissible alert — a warning the user can tap away doesn't
            reliably reach a reviewer either. */}
        <Text style={styles.disclaimer} maxFontSizeMultiplier={1.6}>
          WeightProgram gives general fitness and nutrition information, not medical advice.
          Protein targets here are based only on your body weight and don't account for kidney,
          liver or other health conditions. Talk to your doctor or dietitian about what's right
          for you — especially while you're on GLP-1 medication.
        </Text>

        {!loading && (
          <>
            <Card style={{ gap: 14 }}>
              <Stepper label="Current weight" value={weight} onChange={setWeight}
                step={0.5} min={25} max={350} suffix="kg" allowDecimal />
              <Stepper label="Goal weight (optional)" value={goal} onChange={setGoal}
                step={0.5} min={25} max={350} suffix="kg" allowDecimal />
            </Card>

            <Card style={{ gap: 8 }}>
              <Text style={styles.sectionTitle} maxFontSizeMultiplier={1.3}>Daily protein target</Text>
              <View style={styles.chipRow}>
                {MULTIPLIERS.map((m) => (
                  <Chip
                    key={m.value}
                    label={`${m.label} · ${m.note}`}
                    selected={multiplier === m.value}
                    onPress={() => setMultiplier(m.value)}
                  />
                ))}
              </View>
              {autoTarget != null && !customTarget ? (
                <Text style={styles.targetBig} maxFontSizeMultiplier={1.2}>
                  {autoTarget} g <Text style={styles.targetNote}>(auto: {multiplier} g per kg)</Text>
                </Text>
              ) : null}
              <Stepper label="Custom target (leave 0 for auto)" value={customTarget || "0"}
                onChange={(v) => setCustomTarget(v === "0" ? "" : v)} step={5} min={0} max={400} suffix="g" />
              {effectiveTarget != null && customTarget ? (
                <Text style={styles.targetNote} maxFontSizeMultiplier={1.4}>
                  Using your custom target of {effectiveTarget} g/day.
                </Text>
              ) : null}
            </Card>

            <Card style={{ gap: 10 }}>
              <Text style={styles.sectionTitle} maxFontSizeMultiplier={1.3}>Diet pattern</Text>
              <View style={styles.chipRow}>
                {DIET_PATTERNS.map((d) => (
                  <Chip key={d.key} label={d.label} selected={diet === d.key} onPress={() => setDiet(d.key)} />
                ))}
              </View>
            </Card>

            <Card style={{ gap: 10 }}>
              <Text style={styles.sectionTitle} maxFontSizeMultiplier={1.3}>Restrictions & allergies</Text>
              <Text style={styles.hint} maxFontSizeMultiplier={1.5}>
                These are hard rules — every recipe we ever generate respects them.
              </Text>
              <View style={styles.chipRow}>
                {RESTRICTIONS.map((r) => (
                  <Chip key={r.key} label={r.label} selected={restrictions.includes(r.key)}
                    onPress={() => toggleRestriction(r.key)} />
                ))}
                {restrictions.filter((r) => r.startsWith("custom:")).map((r) => (
                  <Chip key={r} label={`No ${r.slice(7)} ✕`} selected onPress={() => toggleRestriction(r)} />
                ))}
              </View>
              <View style={styles.customRow}>
                <TextInput
                  style={styles.customInput}
                  placeholder="Add your own (e.g. shellfish)"
                  placeholderTextColor={theme.colors.textTertiary}
                  value={customInput}
                  onChangeText={setCustomInput}
                  onSubmitEditing={addCustom}
                  returnKeyType="done"
                  maxFontSizeMultiplier={1.4}
                />
                <Button title="Add" size="small" fullWidth={false} variant="secondary" onPress={addCustom} />
              </View>
            </Card>

            {error ? <Text style={styles.error} maxFontSizeMultiplier={1.4}>{error}</Text> : null}

            <Button title={firstRun ? "Set my target" : "Save profile"} onPress={save} loading={saving} />
            {onBack ? <Button title="Back" variant="ghost" onPress={onBack} /> : null}
          </>
        )}
      </ScrollView>
    </ScreenBackground>
  );
}

function getStyles(theme: Theme) {
  return StyleSheet.create({
    container: { padding: 20, gap: 16, paddingBottom: 40 },
    title: { ...theme.typography.title, color: theme.colors.text, marginTop: 8 },
    subtitle: { ...theme.typography.subhead, color: theme.colors.textSecondary, lineHeight: 20 },
    sectionTitle: { ...theme.typography.headline, color: theme.colors.text },
    targetBig: { fontSize: 30, fontWeight: "800", color: theme.colors.secondary },
    targetNote: { ...theme.typography.footnote, color: theme.colors.textSecondary },
    hint: { ...theme.typography.footnote, color: theme.colors.textTertiary },
    // Medical disclaimer (guideline 1.4.1). textSecondary rather than
    // textTertiary on purpose — this has to stay legible, not decorative.
    disclaimer: {
      ...theme.typography.footnote,
      color: theme.colors.textSecondary,
      lineHeight: 18,
      backgroundColor: theme.colors.backgroundElevated,
      borderRadius: theme.radius.md,
      padding: 12,
    },
    chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
    customRow: { flexDirection: "row", alignItems: "center", gap: 8 },
    customInput: {
      flex: 1,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.colors.border,
      borderRadius: theme.radius.md,
      paddingHorizontal: 12,
      paddingVertical: 10,
      color: theme.colors.text,
      backgroundColor: theme.colors.backgroundElevated2,
      ...theme.typography.body,
    },
    error: { ...theme.typography.subhead, color: theme.colors.danger },
  });
}
