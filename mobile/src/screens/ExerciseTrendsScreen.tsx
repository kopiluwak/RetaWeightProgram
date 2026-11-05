// Per-exercise analytics: searchable exercise picker + trend charts, PRs,
// plateau and PR-projection insights for the chosen lift.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { AnalyticsApi, AnalyticsRange, ExerciseDetail, ExerciseListItem } from "../api";
import { Theme, useTheme } from "../theme";
import { Button, Card, Chip, ChevronGlyph, ScreenBackground } from "../ui";
import { LineChart, WeeklyBars } from "../ui/charts";

const RANGES: AnalyticsRange[] = ["30d", "90d", "6m", "1y", "all"];
const RANGE_LABELS: Record<AnalyticsRange, string> = {
  "30d": "30D",
  "90d": "90D",
  "6m": "6M",
  "1y": "1Y",
  all: "All",
};

/**
 * Exercise Trends (spec S3): search/pick a lift, then per-exercise charts —
 * e1RM trend (headline), weekly volume, best set — with a range selector and
 * a % change headline. Plateau + projection insights live here, not on the
 * dashboard (spec S2).
 */
export default function ExerciseTrendsScreen({
  onBack,
  initialExercise,
}: {
  onBack: () => void;
  initialExercise?: string | null;
}) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const [list, setList] = useState<ExerciseListItem[] | null>(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(initialExercise ?? null);
  const [range, setRange] = useState<AnalyticsRange>("90d");
  const [detail, setDetail] = useState<ExerciseDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    AnalyticsApi.exercises()
      .then(setList)
      .catch(() => setList([]));
  }, []);

  const loadDetail = useCallback(async (name: string, r: AnalyticsRange) => {
    setLoading(true);
    setError(null);
    try {
      setDetail(await AnalyticsApi.exerciseDetail(name, r));
    } catch (e) {
      setDetail(null);
      setError(e instanceof Error ? e.message : "Could not load trends");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selected) loadDetail(selected, range);
  }, [selected, range, loadDetail]);

  const filtered = useMemo(() => {
    if (!list) return [];
    const q = query.trim().toLowerCase();
    return q ? list.filter((e) => e.name.toLowerCase().includes(q)) : list;
  }, [list, query]);

  // ---------- Picker ----------
  if (!selected) {
    return (
      <ScreenBackground onBack={onBack} backLabel="Progress">
        <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
          <Text style={styles.title} maxFontSizeMultiplier={1.2}>Exercise trends</Text>
          <TextInput
            value={query}
            onChangeText={setQuery}
            placeholder="Search exercises…"
            placeholderTextColor={theme.colors.textTertiary}
            style={styles.search}
            autoCorrect={false}
          />
          {list === null ? (
            <ActivityIndicator size="large" color={theme.colors.text} style={{ marginTop: 40 }} />
          ) : filtered.length === 0 ? (
            <Card>
              <Text style={styles.body}>
                {list.length === 0
                  ? "No logged exercises yet. Finish a workout and they'll show up here."
                  : "No exercise matches that search."}
              </Text>
            </Card>
          ) : (
            <Card padded={false}>
              {filtered.map((e, i) => (
                <Pressable
                  key={e.name}
                  onPress={() => setSelected(e.name)}
                  style={[styles.pickRow, i < filtered.length - 1 && styles.pickRowBorder]}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowTitle} numberOfLines={1}>{e.name}</Text>
                    <Text style={styles.caption}>
                      {e.sessions} session{e.sessions === 1 ? "" : "s"} · {e.muscles.join(", ")} · last{" "}
                      {new Date(e.last_performed + "T12:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                    </Text>
                  </View>
                  <ChevronGlyph color={theme.colors.textTertiary} />
                </Pressable>
              ))}
            </Card>
          )}
        </ScrollView>
      </ScreenBackground>
    );
  }

  // ---------- Detail ----------
  const pct = detail?.pct_change ?? null;
  const up = (pct ?? 0) >= 0;
  const series = detail ? (detail.unloaded ? detail.reps_series : detail.e1rm_series) : [];

  return (
    <ScreenBackground onBack={() => { setSelected(null); setDetail(null); }} backLabel="Exercises">
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title} maxFontSizeMultiplier={1.2} numberOfLines={2}>{selected}</Text>

        <View style={styles.rangeRow}>
          {RANGES.map((r) => (
            <Chip key={r} label={RANGE_LABELS[r]} selected={range === r} onPress={() => setRange(r)} />
          ))}
        </View>

        {loading ? (
          <ActivityIndicator size="large" color={theme.colors.text} style={{ marginTop: 40 }} />
        ) : error ? (
          <Card>
            <Text style={styles.body}>{error}</Text>
          </Card>
        ) : detail ? (
          <>
            <Card>
              <View style={{ flexDirection: "row", alignItems: "baseline", justifyContent: "space-between" }}>
                <Text style={styles.cardTitle}>{detail.unloaded ? "Best reps" : "Estimated 1RM"}</Text>
                {pct != null && (
                  <Text style={{ fontSize: 16, fontWeight: "800", color: up ? theme.colors.success : theme.colors.danger }}>
                    {up ? "+" : ""}
                    {pct}%
                  </Text>
                )}
              </View>
              <LineChart points={series} color={theme.colors.accent} />
              {detail.prs.e1rm && !detail.unloaded && (
                <Text style={styles.caption}>
                  All-time best: {detail.prs.e1rm.value} est. 1RM (
                  {new Date(detail.prs.e1rm.date + "T12:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })})
                </Text>
              )}
            </Card>

            {(detail.projection || detail.plateau) && (
              <Card accentColor={detail.projection ? theme.colors.success : theme.colors.warning}>
                {detail.projection ? (
                  <>
                    <Text style={styles.cardTitle}>On pace</Text>
                    <Text style={styles.body}>
                      Keep this trend and you're looking at ~{detail.projection.target} around{" "}
                      {new Date(detail.projection.date + "T12:00:00").toLocaleDateString(undefined, { month: "long", day: "numeric" })}.
                    </Text>
                  </>
                ) : (
                  <>
                    <Text style={styles.cardTitle}>Plateau watch</Text>
                    <Text style={styles.body}>{detail.plateau_message}</Text>
                  </>
                )}
              </Card>
            )}

            <Card>
              <Text style={styles.cardTitle}>Weekly volume</Text>
              <WeeklyBars
                bars={detail.volume_weekly.map((p) => ({
                  label: new Date(p.date + "T12:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" }),
                  value: p.value,
                }))}
                height={90}
                showLabels
                formatValue={(v) => v.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              />
            </Card>

            {!detail.unloaded && detail.best_sets.length > 0 && (
              <Card>
                <Text style={styles.cardTitle}>Best set per session</Text>
                {detail.best_sets.slice(-8).reverse().map((b, i) => (
                  <View key={i} style={styles.listRow}>
                    <Text style={[styles.caption, { flex: 1, marginTop: 0 }]}>
                      {new Date(b.date + "T12:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
                    </Text>
                    <Text style={styles.rowTitle}>
                      {b.weight} × {b.reps}
                    </Text>
                  </View>
                ))}
                {detail.prs.weight && (
                  <Text style={[styles.caption, { marginTop: 8 }]}>
                    Heaviest ever: {detail.prs.weight.weight} × {detail.prs.weight.reps}
                  </Text>
                )}
              </Card>
            )}
          </>
        ) : null}
      </ScrollView>
    </ScreenBackground>
  );
}

function getStyles(theme: Theme) {
  return StyleSheet.create({
    container: { padding: 20, paddingTop: 8, gap: 14, flexGrow: 1 },
    title: { fontSize: 30, fontWeight: "800", color: theme.colors.text, letterSpacing: -0.5 },
    backLink: { fontSize: 15, fontWeight: "600", color: theme.colors.accent },
    search: {
      backgroundColor: theme.colors.backgroundElevated,
      borderColor: theme.colors.border,
      borderWidth: StyleSheet.hairlineWidth,
      borderRadius: theme.radius.md,
      paddingHorizontal: 14,
      paddingVertical: 10,
      fontSize: 16,
      color: theme.colors.text,
    },
    rangeRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
    cardTitle: { fontSize: 17, fontWeight: "700", color: theme.colors.text, marginBottom: 8 },
    body: { fontSize: 15, color: theme.colors.textSecondary, lineHeight: 21 },
    caption: { fontSize: 12, color: theme.colors.textTertiary, marginTop: 4 },
    rowTitle: { fontSize: 15, fontWeight: "600", color: theme.colors.text },
    listRow: {
      flexDirection: "row",
      alignItems: "center",
      paddingVertical: 7,
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: theme.colors.border,
    },
    pickRow: { flexDirection: "row", alignItems: "center", paddingHorizontal: 16, paddingVertical: 12 },
    pickRowBorder: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: theme.colors.border },
  });
}
