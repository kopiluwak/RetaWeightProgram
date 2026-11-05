// Neutron: Recipe & Meal Builder.
// Filters + pantry-first generation, per-recipe detail with a "Make it
// Vegan/Vegetarian" instant regenerate, one-tap meal logging, saving, and the
// "Surprise Me" full-day plan that hits the protein target.
import React, { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import * as Haptics from "expo-haptics";
import { DayPlan, NutritionApi, NutritionProfile, Recipe } from "../api";
import { Theme, useTheme } from "../theme";
import { Badge, Button, Card, Chip, ScreenBackground } from "../ui";

/** "42% of your daily protein" caption for a recipe card, if a target is set. */
function pctOfTarget(recipe: Recipe, target: number | null): string | null {
  if (!target) return null;
  return `${Math.round((100 * recipe.protein_g) / target)}% of your daily protein`;
}

// ------------------------------------------------------------ detail view

/** Full recipe view: macros, ingredients, steps, veganize/log/save actions. */
function RecipeDetail({
  recipe,
  target,
  source,
  onClose,
  onReplace,
}: {
  recipe: Recipe;
  target: number | null;
  source: string;
  onClose: () => void;
  onReplace: (r: Recipe) => void;
}) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const [adapting, setAdapting] = useState<string | null>(null);
  const [logging, setLogging] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function adapt(mode: "vegan" | "vegetarian") {
    setError(null);
    setAdapting(mode);
    try {
      const res = await NutritionApi.adaptRecipe(recipe, mode);
      if (res.recipes[0]) onReplace(res.recipes[0]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setAdapting(null);
    }
  }

  async function logMeal() {
    setLogging(true);
    try {
      const res = await NutritionApi.logProtein(recipe.protein_g, recipe.title, "recipe", recipe.calories);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      Alert.alert(
        "Logged!",
        `${Math.round(recipe.protein_g)} g protein added — you're at ${Math.round(res.today_total_g)} g today.` +
          (res.newly_earned_badges.length ? `\n\nBadge earned: ${res.newly_earned_badges.join(", ").replace(/_/g, " ")} 🏅` : "")
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLogging(false);
    }
  }

  async function save() {
    setSaving(true);
    try {
      await NutritionApi.saveRecipe(recipe, source);
      Alert.alert("Saved", "Recipe saved to your collection.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const pantryCount = recipe.ingredients.filter((i) => i.from_pantry).length;

  return (
    <ScreenBackground onBack={onClose} backLabel="Recipes">
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title} maxFontSizeMultiplier={1.2}>{recipe.title}</Text>
        {recipe.description ? (
          <Text style={styles.subtitle} maxFontSizeMultiplier={1.4}>{recipe.description}</Text>
        ) : null}

        <View style={styles.badgeRow}>
          <Badge label={`${Math.round(recipe.protein_g)} g protein`} tone="success" />
          <Badge label={`${Math.round(recipe.calories)} kcal`} tone="neutral" />
          <Badge label={`C ${Math.round(recipe.carbs_g)} g · F ${Math.round(recipe.fat_g)} g`} tone="neutral" />
        </View>
        {pctOfTarget(recipe, target) ? (
          <Text style={styles.pctText} maxFontSizeMultiplier={1.4}>
            This meal covers {pctOfTarget(recipe, target)} 💪
          </Text>
        ) : null}
        <View style={styles.badgeRow}>
          <Badge label={`Prep ${recipe.prep_minutes} min`} tone="neutral" />
          <Badge label={`Cook ${recipe.cook_minutes} min`} tone="neutral" />
          <Badge label={recipe.difficulty.toUpperCase()} tone="accent" />
          <Badge label={`Serves ${recipe.servings}`} tone="neutral" />
          {recipe.is_vegan ? <Badge label="VEGAN" tone="success" /> :
            recipe.is_vegetarian ? <Badge label="VEGETARIAN" tone="success" /> : null}
        </View>

        {!recipe.is_vegan ? (
          <Card style={{ gap: 8 }}>
            <Text style={styles.sectionTitle} maxFontSizeMultiplier={1.3}>Make it plant-based</Text>
            <Text style={styles.hint} maxFontSizeMultiplier={1.5}>
              Instantly rebuilds this recipe with plant proteins while keeping your scanned
              ingredients in play.
            </Text>
            <View style={{ flexDirection: "row", gap: 10 }}>
              <View style={{ flex: 1 }}>
                <Button title="Vegan" size="medium" variant="secondary"
                  onPress={() => adapt("vegan")} loading={adapting === "vegan"} />
              </View>
              {!recipe.is_vegetarian ? (
                <View style={{ flex: 1 }}>
                  <Button title="Vegetarian" size="medium" variant="secondary"
                    onPress={() => adapt("vegetarian")} loading={adapting === "vegetarian"} />
                </View>
              ) : null}
            </View>
          </Card>
        ) : null}

        <Card style={{ gap: 6 }}>
          <Text style={styles.sectionTitle} maxFontSizeMultiplier={1.3}>
            Ingredients{pantryCount > 0 ? ` · ${pantryCount} from your kitchen` : ""}
          </Text>
          {recipe.ingredients.map((ing, i) => (
            <View key={i} style={styles.ingRow}>
              <Text style={styles.ingText} maxFontSizeMultiplier={1.5}>
                {ing.quantity ? `${ing.quantity} ` : ""}{ing.name}
              </Text>
              {ing.from_pantry ? <Badge label="IN YOUR KITCHEN" tone="success" /> : null}
            </View>
          ))}
        </Card>

        <Card style={{ gap: 10 }}>
          <Text style={styles.sectionTitle} maxFontSizeMultiplier={1.3}>Steps</Text>
          {recipe.steps.map((s, i) => (
            <View key={i} style={{ flexDirection: "row", gap: 10 }}>
              <Text style={styles.stepNum} maxFontSizeMultiplier={1.3}>{i + 1}</Text>
              <Text style={[styles.ingText, { flex: 1 }]} maxFontSizeMultiplier={1.5}>{s}</Text>
            </View>
          ))}
        </Card>

        {/* Guideline 1.4.1. This recipe came out of an LLM under dietary
            constraints the user declared, and neutron_recipes.py treats
            Alpha-Gal as "a life-safety allergy, not a preference". The model
            is instructed to honour those constraints and the result is
            re-validated, but neither is a guarantee — so the user is told
            plainly to check for themselves. Placed directly ABOVE the
            "I made this" and "Save" actions: it has to be read before the
            food is eaten, not found after. */}
        <Text style={styles.disclaimer} maxFontSizeMultiplier={1.6}>
          Recipes are AI-generated and can be wrong. Always check the ingredients yourself before
          cooking or eating. If you have a food allergy, don't rely on this app alone to keep an
          allergen out of your meal.
        </Text>

        {error ? <Text style={styles.error} maxFontSizeMultiplier={1.4}>{error}</Text> : null}
        <Button title={`I made this — log ${Math.round(recipe.protein_g)} g protein`}
          variant="accent" onPress={logMeal} loading={logging} />
        <Button title="Save recipe" variant="secondary" onPress={save} loading={saving} />
      </ScrollView>
    </ScreenBackground>
  );
}

// -------------------------------------------------------------- main screen

export default function RecipesScreen({
  onBack,
  autoGenerate,
}: {
  onBack: () => void;
  /** True when arriving from a fresh kitchen scan — generate immediately. */
  autoGenerate?: boolean;
}) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const [profile, setProfile] = useState<NutritionProfile | null>(null);
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [dayPlan, setDayPlan] = useState<DayPlan | null>(null);
  const [selected, setSelected] = useState<Recipe | null>(null);
  const [loading, setLoading] = useState(false);
  const [surprising, setSurprising] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [highProtein, setHighProtein] = useState(true); // >= 30 g / serving
  const [usePantry, setUsePantry] = useState(true);
  const [dietOverride, setDietOverride] = useState<string | null>(null);

  useEffect(() => {
    NutritionApi.profile().then(setProfile).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
    if (autoGenerate) generate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function generate() {
    setError(null);
    setLoading(true);
    setDayPlan(null);
    try {
      const res = await NutritionApi.generateRecipes({
        use_pantry: usePantry,
        count: 4,
        min_protein_per_serving: highProtein ? 30 : 15,
        diet_pattern: dietOverride,
      });
      setRecipes(res.recipes);
      if (res.newly_earned_badges.length > 0) {
        Alert.alert("Badge earned! 🏅", res.newly_earned_badges.join(", ").replace(/_/g, " "));
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function surprise() {
    setError(null);
    setSurprising(true);
    setRecipes([]);
    try {
      setDayPlan(await NutritionApi.surpriseMe());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSurprising(false);
    }
  }

  if (selected) {
    return (
      <RecipeDetail
        recipe={selected}
        target={profile?.protein_target_g ?? null}
        source={usePantry ? "pantry_scan" : "builder"}
        onClose={() => setSelected(null)}
        onReplace={(r) => setSelected(r)}
      />
    );
  }

  const target = profile?.protein_target_g ?? null;
  const activeRestrictions = profile?.restrictions ?? [];

  return (
    <ScreenBackground onBack={onBack} backLabel="Nutrition">
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title} maxFontSizeMultiplier={1.2}>Recipes & Meal Builder</Text>

        <Card style={{ gap: 10 }}>
          <Text style={styles.sectionTitle} maxFontSizeMultiplier={1.3}>Filters</Text>
          <View style={styles.chipRow}>
            <Chip label="High-protein (30 g+)" selected={highProtein} onPress={() => setHighProtein(!highProtein)} />
            <Chip label="Use my kitchen first" selected={usePantry} onPress={() => setUsePantry(!usePantry)} />
          </View>
          <View style={styles.chipRow}>
            {["vegan", "vegetarian", "pescatarian"].map((d) => (
              <Chip key={d} label={d[0].toUpperCase() + d.slice(1)} selected={dietOverride === d}
                onPress={() => setDietOverride(dietOverride === d ? null : d)} />
            ))}
          </View>
          {activeRestrictions.length > 0 ? (
            <Text style={styles.hint} maxFontSizeMultiplier={1.5}>
              Always applied: {activeRestrictions.map((r) => r.replace("custom:", "no ").replace(/_/g, " ")).join(", ")}.
              Edit these in your protein profile.
            </Text>
          ) : null}
        </Card>

        <Button title="Generate recipes" variant="accent" onPress={generate} loading={loading} />
        <Button title="🎲 Surprise Me — plan my whole day" variant="secondary"
          onPress={surprise} loading={surprising} />

        {error ? <Text style={styles.error} maxFontSizeMultiplier={1.4}>{error}</Text> : null}
        {(loading || surprising) && (
          <View style={{ alignItems: "center", gap: 8, marginTop: 8 }}>
            <ActivityIndicator color={theme.colors.text} />
            <Text style={styles.hint} maxFontSizeMultiplier={1.5}>
              Building protein-dense ideas from your kitchen…
            </Text>
          </View>
        )}

        {dayPlan ? (
          <Card style={{ gap: 10 }} accentColor={theme.colors.secondary}>
            <Text style={styles.sectionTitle} maxFontSizeMultiplier={1.3}>Your day, planned</Text>
            <View style={styles.badgeRow}>
              <Badge label={`${Math.round(dayPlan.total_protein_g)} g protein total`} tone="success" />
              {target ? (
                <Badge label={`${Math.round((100 * dayPlan.total_protein_g) / target)}% of target`}
                  tone={dayPlan.total_protein_g >= target ? "success" : "warning"} />
              ) : null}
            </View>
            {dayPlan.note ? <Text style={styles.hint} maxFontSizeMultiplier={1.5}>{dayPlan.note}</Text> : null}
            {dayPlan.meals.map((m, i) => (
              <Pressable key={i} onPress={() => setSelected(m.recipe)} accessibilityRole="button">
                <View style={styles.mealRow}>
                  <Text style={styles.mealSlot} maxFontSizeMultiplier={1.3}>{m.slot.toUpperCase()}</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.mealTitle} maxFontSizeMultiplier={1.4}>{m.recipe.title}</Text>
                    <Text style={styles.hint} maxFontSizeMultiplier={1.5}>
                      {Math.round(m.recipe.protein_g)} g protein · {Math.round(m.recipe.calories)} kcal
                    </Text>
                  </View>
                </View>
              </Pressable>
            ))}
          </Card>
        ) : null}

        {recipes.map((r, i) => (
          <Pressable key={i} onPress={() => setSelected(r)} accessibilityRole="button">
            <Card style={{ gap: 8 }}>
              <Text style={styles.recipeTitle} maxFontSizeMultiplier={1.3}>{r.title}</Text>
              <View style={styles.badgeRow}>
                <Badge label={`${Math.round(r.protein_g)} g protein`} tone="success" />
                <Badge label={`${Math.round(r.calories)} kcal`} tone="neutral" />
                <Badge label={`${r.prep_minutes + r.cook_minutes} min`} tone="neutral" />
                <Badge label={r.difficulty.toUpperCase()} tone="accent" />
              </View>
              {pctOfTarget(r, target) ? (
                <Text style={styles.pctText} maxFontSizeMultiplier={1.4}>{pctOfTarget(r, target)}</Text>
              ) : null}
              {r.tags.length > 0 ? (
                <Text style={styles.hint} maxFontSizeMultiplier={1.5}>{r.tags.join(" · ")}</Text>
              ) : null}
            </Card>
          </Pressable>
        ))}
      </ScrollView>
    </ScreenBackground>
  );
}

function getStyles(theme: Theme) {
  return StyleSheet.create({
    container: { padding: 20, gap: 14, paddingBottom: 40 },
    backText: { ...theme.typography.headline, color: theme.colors.accent },
    title: { ...theme.typography.title, color: theme.colors.text },
    subtitle: { ...theme.typography.subhead, color: theme.colors.textSecondary, lineHeight: 20 },
    sectionTitle: { ...theme.typography.headline, color: theme.colors.text },
    recipeTitle: { ...theme.typography.title2, color: theme.colors.text },
    badgeRow: { flexDirection: "row", flexWrap: "wrap", gap: 6, alignItems: "center" },
    pctText: { ...theme.typography.subhead, color: theme.colors.secondary, fontWeight: "700" },
    chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
    hint: { ...theme.typography.footnote, color: theme.colors.textTertiary },
    // AI-content + allergy disclaimer (guideline 1.4.1). textSecondary, not
    // textTertiary — a safety notice must not read as fine print.
    disclaimer: {
      ...theme.typography.footnote,
      color: theme.colors.textSecondary,
      lineHeight: 18,
      backgroundColor: theme.colors.backgroundElevated,
      borderRadius: theme.radius.md,
      padding: 12,
    },
    error: { ...theme.typography.subhead, color: theme.colors.danger },
    ingRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
    ingText: { ...theme.typography.body, color: theme.colors.text },
    stepNum: { ...theme.typography.headline, color: theme.colors.accent, width: 22 },
    mealRow: { flexDirection: "row", gap: 12, alignItems: "center", paddingVertical: 4 },
    mealSlot: { ...theme.typography.caption, color: theme.colors.secondary, width: 86 },
    mealTitle: { ...theme.typography.headline, color: theme.colors.text },
  });
}
