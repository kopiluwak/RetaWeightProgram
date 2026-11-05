// Neutron: weekly protein tracker + gamification.
// Daily bars vs target, 4-week trend, streaks, level, muscle-preservation
// score, and the badge cabinet. All aggregation is server-side (/nutrition/summary).
import React, { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { NutritionApi, NutritionSummary, ProteinLogEntry } from "../api";
import { Theme, useTheme } from "../theme";
import { Badge, Card, ProgressBar, ProteinProgress, ScreenBackground } from "../ui";
import LineChart from "../ui/charts/LineChart";
import WeeklyBars from "../ui/charts/WeeklyBars";

/** Single-letter weekday label under each daily bar. */
function dayLetter(iso: string): string {
  return ["S", "M", "T", "W", "T", "F", "S"][new Date(iso + "T12:00:00").getDay()];
}

export default function ProteinTrackerScreen({ onBack }: { onBack: () => void }) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const [summary, setSummary] = useState<NutritionSummary | null>(null);
  const [history, setHistory] = useState<ProteinLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([NutritionApi.summary(), NutritionApi.logHistory(7)])
      .then(([s, h]) => {
        setSummary(s);
        setHistory(h);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // Remove an entry logged by mistake. Confirm first (deletes are silent /
  // irreversible), then drop it locally and re-pull the summary so today's
  // total, streaks, and badges reflect the removal.
  function confirmDelete(entry: ProteinLogEntry) {
    Alert.alert(
      "Delete entry?",
      `Remove “${entry.label || "Protein"}” (${Math.round(entry.grams)} g) from your log?`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete",
          style: "destructive",
          onPress: async () => {
            setDeletingId(entry.id);
            try {
              await NutritionApi.deleteLog(entry.id);
              setHistory((prev) => prev.filter((e) => e.id !== entry.id));
              const s = await NutritionApi.summary();
              setSummary(s);
            } catch (e) {
              Alert.alert("Couldn't delete", (e as Error).message);
            } finally {
              setDeletingId(null);
            }
          },
        },
      ],
    );
  }

  const target = summary?.target_g ?? 0;
  const earned = summary?.badges.filter((b) => b.earned) ?? [];
  const locked = summary?.badges.filter((b) => !b.earned) ?? [];
  const levelProgress =
    summary && summary.next_level_at
      ? Math.min(1, summary.total_hit_days / summary.next_level_at)
      : 1;

  return (
    <ScreenBackground onBack={onBack} backLabel="Nutrition">
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title} maxFontSizeMultiplier={1.2}>Protein Tracker</Text>

        {loading ? (
          <ActivityIndicator size="large" color={theme.colors.text} style={{ marginTop: 60 }} />
        ) : error ? (
          <Text style={styles.error} maxFontSizeMultiplier={1.4}>{error}</Text>
        ) : summary ? (
          <>
            {/* Today, front and center: the animated bar is the screen's hero. */}
            <Card style={{ gap: 4 }}>
              <Text style={styles.sectionTitle} maxFontSizeMultiplier={1.3}>Today</Text>
              <ProteinProgress
                grams={summary.today_g}
                targetG={summary.target_g}
                weekAvgG={summary.week_avg_g}
                xpHint="+25 XP"
              />
              <Text style={styles.hint} maxFontSizeMultiplier={1.5}>{summary.message}</Text>
            </Card>

            <Card style={{ gap: 10 }}>
              <Text style={styles.sectionTitle} maxFontSizeMultiplier={1.3}>This week</Text>
              <WeeklyBars
                bars={summary.week_days.map((d, i) => ({
                  label: dayLetter(d.date),
                  value: d.grams,
                  highlight: d.hit || i === summary.week_days.length - 1,
                }))}
                maxValue={target || undefined}
                height={92}
                showLabels
                formatValue={(v) => `${Math.round(v)} g`}
              />
              <Text style={styles.hint} maxFontSizeMultiplier={1.5}>
                {target
                  ? `Target line: ${Math.round(target)} g/day · weekly average ${summary.week_avg_g} g`
                  : "Set your weight to get a daily target."}
              </Text>
            </Card>

            <Card style={{ gap: 10 }}>
              <Text style={styles.sectionTitle} maxFontSizeMultiplier={1.3}>4-week trend</Text>
              <LineChart
                points={summary.trend_weeks.map((w) => ({ date: w.week_start, value: w.avg_grams }))}
                height={120}
                color={theme.colors.secondary}
                formatValue={(v) => `${Math.round(v)} g/day avg`}
              />
            </Card>

            <View style={styles.statRow}>
              <StatCard theme={theme} value={`🔥 ${summary.daily_streak}`} label="day streak"
                sub={`best ${summary.best_daily_streak}`} />
              <StatCard theme={theme} value={`${summary.weekly_streak}`} label="week streak"
                sub="5+ hit days/wk" />
              <StatCard theme={theme} value={`${summary.muscle_score}`} label="muscle score"
                sub="28-day consistency" />
            </View>

            <Card style={{ gap: 8 }}>
              <View style={styles.rowBetween}>
                <Text style={styles.sectionTitle} maxFontSizeMultiplier={1.3}>
                  Level {summary.level} — {summary.level_title}
                </Text>
                <Badge label={`${summary.total_hit_days} target days`} tone="success" />
              </View>
              <ProgressBar progress={levelProgress} color={theme.colors.accent} />
              <Text style={styles.hint} maxFontSizeMultiplier={1.5}>
                {summary.next_level_at
                  ? `${summary.next_level_at - summary.total_hit_days} more target day${summary.next_level_at - summary.total_hit_days === 1 ? "" : "s"} to the next level.`
                  : "Max level. Absolute legend."}
              </Text>
            </Card>

            <Card style={{ gap: 10 }}>
              <Text style={styles.sectionTitle} maxFontSizeMultiplier={1.3}>
                Badges · {earned.length}/{summary.badges.length}
              </Text>
              {earned.map((b) => (
                <View key={b.key} style={styles.badgeLine}>
                  <Text style={{ fontSize: 20 }}>🏅</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.badgeName} maxFontSizeMultiplier={1.4}>{b.name}</Text>
                    <Text style={styles.hint} maxFontSizeMultiplier={1.5}>{b.description}</Text>
                  </View>
                </View>
              ))}
              {locked.map((b) => (
                <View key={b.key} style={[styles.badgeLine, { opacity: 0.45 }]}>
                  <Text style={{ fontSize: 20 }}>🔒</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.badgeName} maxFontSizeMultiplier={1.4}>{b.name}</Text>
                    <Text style={styles.hint} maxFontSizeMultiplier={1.5}>{b.description}</Text>
                  </View>
                </View>
              ))}
            </Card>

            {history.length > 0 ? (
              <Card style={{ gap: 8 }}>
                <Text style={styles.sectionTitle} maxFontSizeMultiplier={1.3}>Recent entries</Text>
                <Text style={styles.hint} maxFontSizeMultiplier={1.5}>Tap ✕ (or long-press a row) to remove an entry.</Text>
                {history.slice(0, 10).map((e) => (
                  <Pressable
                    key={e.id}
                    onLongPress={() => confirmDelete(e)}
                    delayLongPress={350}
                    style={styles.rowBetween}
                  >
                    <Text style={styles.entryLabel} numberOfLines={1} maxFontSizeMultiplier={1.4}>
                      {e.label || "Protein"}
                    </Text>
                    <Text style={styles.entryGrams} maxFontSizeMultiplier={1.4}>
                      {Math.round(e.grams)} g
                    </Text>
                    <Pressable
                      onPress={() => confirmDelete(e)}
                      disabled={deletingId === e.id}
                      hitSlop={10}
                      accessibilityRole="button"
                      accessibilityLabel={`Delete ${e.label || "protein"} entry`}
                      style={styles.deleteBtn}
                    >
                      {deletingId === e.id ? (
                        <ActivityIndicator size="small" color={theme.colors.danger} />
                      ) : (
                        <Text style={styles.deleteIcon} maxFontSizeMultiplier={1.3}>✕</Text>
                      )}
                    </Pressable>
                  </Pressable>
                ))}
              </Card>
            ) : null}
          </>
        ) : null}
      </ScrollView>
    </ScreenBackground>
  );
}

function StatCard({ theme, value, label, sub }: { theme: Theme; value: string; label: string; sub: string }) {
  const styles = useMemo(() => getStyles(theme), [theme]);
  return (
    <Card style={styles.statCard} padded={false}>
      <Text style={styles.statValue} maxFontSizeMultiplier={1.2}>{value}</Text>
      <Text style={styles.statLabel} maxFontSizeMultiplier={1.4}>{label}</Text>
      <Text style={styles.statSub} maxFontSizeMultiplier={1.5}>{sub}</Text>
    </Card>
  );
}

function getStyles(theme: Theme) {
  return StyleSheet.create({
    container: { padding: 20, gap: 14, paddingBottom: 40 },
    backText: { ...theme.typography.headline, color: theme.colors.accent },
    title: { ...theme.typography.title, color: theme.colors.text },
    sectionTitle: { ...theme.typography.headline, color: theme.colors.text },
    hint: { ...theme.typography.footnote, color: theme.colors.textTertiary },
    error: { ...theme.typography.subhead, color: theme.colors.danger },
    rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 },
    statRow: { flexDirection: "row", gap: 10 },
    statCard: { flex: 1, alignItems: "center", paddingVertical: 14, paddingHorizontal: 6 },
    statValue: { fontSize: 22, fontWeight: "800", color: theme.colors.text },
    statLabel: { ...theme.typography.subhead, color: theme.colors.textSecondary, marginTop: 2 },
    statSub: { ...theme.typography.footnote, color: theme.colors.textTertiary, marginTop: 1, textAlign: "center" },
    badgeLine: { flexDirection: "row", gap: 10, alignItems: "center" },
    badgeName: { ...theme.typography.headline, color: theme.colors.text },
    entryLabel: { ...theme.typography.body, color: theme.colors.text, flex: 1 },
    entryGrams: { ...theme.typography.headline, color: theme.colors.secondary },
    deleteBtn: { width: 28, height: 28, alignItems: "center", justifyContent: "center" },
    deleteIcon: { ...theme.typography.headline, color: theme.colors.textTertiary },
  });
}
