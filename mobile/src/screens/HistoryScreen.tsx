// Workout history: consistency heatmap + filterable, expandable session list.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { AnalyticsApi, AnalyticsHistory, AnalyticsRange, WorkoutApi, WorkoutSession } from "../api";
import { Theme, useTheme } from "../theme";
import { Button, Card, Chip, ScreenBackground } from "../ui";
import { CalendarHeatmap } from "../ui/charts";

const RANGES: AnalyticsRange[] = ["90d", "6m", "1y", "all"];
const RANGE_LABELS: Record<string, string> = { "90d": "90D", "6m": "6M", "1y": "1Y", all: "All" };
const MUSCLES = ["chest", "back", "quads", "hamstrings", "glutes", "shoulders", "biceps", "triceps", "calves", "core"];

/**
 * Workout History (spec S5): calendar heatmap (intensity = sets/day) above a
 * filterable session list. Tapping a heatmap day filters the list to that
 * day; tapping a session expands its full set log inline.
 */
export default function HistoryScreen({ onBack }: { onBack: () => void }) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const [range, setRange] = useState<AnalyticsRange>("6m");
  const [muscle, setMuscle] = useState<string | null>(null);
  const [exercise, setExercise] = useState("");
  const [data, setData] = useState<AnalyticsHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dayFilter, setDayFilter] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [detail, setDetail] = useState<WorkoutSession | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await AnalyticsApi.history(range, exercise.trim() || undefined, muscle ?? undefined));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load history");
    } finally {
      setLoading(false);
    }
  }, [range, muscle, exercise]);

  useEffect(() => {
    const t = setTimeout(load, exercise ? 300 : 0); // debounce typing
    return () => clearTimeout(t);
  }, [load, exercise]);

  /** Expand/collapse a session row, lazily fetching its full set log. */
  async function toggleSession(id: string) {
    if (expanded === id) {
      setExpanded(null);
      setDetail(null);
      return;
    }
    setExpanded(id);
    setDetail(null);
    setDetailLoading(true);
    try {
      setDetail(await WorkoutApi.get(id));
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }

  const sessions = useMemo(() => {
    if (!data) return [];
    return dayFilter ? data.sessions.filter((s) => s.date === dayFilter) : data.sessions;
  }, [data, dayFilter]);

  return (
    <ScreenBackground onBack={onBack} backLabel="Progress">
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Text style={styles.title} maxFontSizeMultiplier={1.2}>History</Text>

        <View style={styles.rangeRow}>
          {RANGES.map((r) => (
            <Chip key={r} label={RANGE_LABELS[r]} selected={range === r} onPress={() => { setRange(r); setDayFilter(null); }} />
          ))}
        </View>

        {loading && !data ? (
          <ActivityIndicator size="large" color={theme.colors.text} style={{ marginTop: 40 }} />
        ) : error ? (
          <Card>
            <Text style={styles.body}>{error}</Text>
            <Button title="Try again" onPress={load} variant="ghost" size="medium" />
          </Card>
        ) : data ? (
          <>
            <Card>
              <Text style={styles.cardTitle}>Training days</Text>
              <CalendarHeatmap
                days={data.days.map((d) => ({ date: d.date, sets: d.sets }))}
                weeks={26}
                onDayPress={(d) => setDayFilter((cur) => (cur === d ? null : d))}
              />
              {dayFilter && (
                <Pressable onPress={() => setDayFilter(null)}>
                  <Text style={[styles.caption, { color: theme.colors.accent, marginTop: 6 }]}>
                    Showing {new Date(dayFilter + "T12:00:00").toLocaleDateString(undefined, { month: "long", day: "numeric" })} — tap to clear
                  </Text>
                </Pressable>
              )}
            </Card>

            <TextInput
              value={exercise}
              onChangeText={setExercise}
              placeholder="Filter by exercise…"
              placeholderTextColor={theme.colors.textTertiary}
              style={styles.search}
              autoCorrect={false}
            />
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
              {MUSCLES.map((m) => (
                <Chip
                  key={m}
                  label={m.charAt(0).toUpperCase() + m.slice(1)}
                  selected={muscle === m}
                  onPress={() => setMuscle((cur) => (cur === m ? null : m))}
                />
              ))}
            </ScrollView>

            {sessions.length === 0 ? (
              <Card>
                <Text style={styles.body}>
                  {data.sessions.length === 0 ? "No workouts in this window yet." : "Nothing matches those filters."}
                </Text>
              </Card>
            ) : (
              sessions.map((s) => (
                <Pressable key={s.id} onPress={() => toggleSession(s.id)}>
                  <Card accentColor={expanded === s.id ? theme.colors.accent : undefined}>
                    <View style={{ flexDirection: "row", alignItems: "center" }}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.rowTitle}>
                          {new Date(s.date + "T12:00:00").toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" })}
                        </Text>
                        <Text style={styles.caption} numberOfLines={1}>
                          {s.day_name ? `${s.day_name} · ` : ""}
                          {s.set_count} sets · vol {s.volume.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                        </Text>
                      </View>
                      <Text style={{ color: theme.colors.textTertiary, fontSize: 13 }}>
                        {expanded === s.id ? "▾" : "▸"}
                      </Text>
                    </View>

                    {expanded === s.id && (
                      <View style={{ marginTop: 10 }}>
                        {detailLoading ? (
                          <ActivityIndicator color={theme.colors.text} />
                        ) : detail ? (
                          groupSets(detail).map(([name, sets]) => (
                            <View key={name} style={{ marginBottom: 8 }}>
                              <Text style={[styles.rowTitle, { fontSize: 14 }]}>{name}</Text>
                              {sets.map((x) => (
                                <Text key={x.id} style={styles.caption}>
                                  Set {x.set_number}: {x.weight != null ? `${x.weight} × ` : ""}
                                  {x.reps} reps · RIR {x.rir}
                                </Text>
                              ))}
                            </View>
                          ))
                        ) : (
                          <Text style={styles.caption}>Couldn't load this session.</Text>
                        )}
                      </View>
                    )}
                  </Card>
                </Pressable>
              ))
            )}
          </>
        ) : null}
      </ScrollView>
    </ScreenBackground>
  );
}

function groupSets(s: WorkoutSession): [string, WorkoutSession["sets"]][] {
  const m = new Map<string, WorkoutSession["sets"]>();
  for (const x of s.sets) {
    const arr = m.get(x.exercise_name) ?? [];
    arr.push(x);
    m.set(x.exercise_name, arr);
  }
  return [...m.entries()];
}

function getStyles(theme: Theme) {
  return StyleSheet.create({
    container: { padding: 20, paddingTop: 8, gap: 14, flexGrow: 1 },
    title: { fontSize: 34, fontWeight: "800", color: theme.colors.text, letterSpacing: -0.5 },
    rangeRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
    cardTitle: { fontSize: 17, fontWeight: "700", color: theme.colors.text, marginBottom: 8 },
    body: { fontSize: 15, color: theme.colors.textSecondary, lineHeight: 21 },
    caption: { fontSize: 12, color: theme.colors.textTertiary, marginTop: 2 },
    rowTitle: { fontSize: 15, fontWeight: "600", color: theme.colors.text },
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
  });
}
