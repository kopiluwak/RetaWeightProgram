// Progress dashboard: consistency, volume, PRs, most-improved and muscle-focus
// cards fed by /analytics/summary, with user-reorderable card layout.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import * as SecureStore from "expo-secure-store";
import { AnalyticsApi, AnalyticsSummary } from "../api";
import { Theme, useTheme } from "../theme";
import { Button, Card, ChevronGlyph, ScreenBackground, WeeklyBadge } from "../ui";
import { Donut, WeeklyBars, musclePalette } from "../ui/charts";
import { usePrShare } from "../ui/PrShareCard";

const ORDER_KEY = "progress_card_order";
const CARD_IDS = ["consistency", "volume", "prs", "improved", "muscles"] as const;
type CardId = (typeof CARD_IDS)[number];

const CARD_TITLES: Record<CardId, string> = {
  consistency: "Consistency",
  volume: "Volume",
  prs: "Recent PRs",
  improved: "Most improved",
  muscles: "Muscle focus",
};

/** Thousands-separated integer for volume figures. */
function fmt(n: number): string {
  return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

/** "quads" -> "Quads" for display. */
function prettyMuscle(m: string): string {
  return m.charAt(0).toUpperCase() + m.slice(1);
}

/**
 * Progress dashboard (spec S2): five reorderable cards + nav rows to the
 * Exercise Trends and History screens. Card order is a personal preference,
 * kept on-device in SecureStore (spec S2b).
 */
export default function ProgressScreen({
  onBack,
  onOpenTrends,
  onOpenHistory,
  onOpenExercise,
}: {
  onBack: () => void;
  onOpenTrends: () => void;
  onOpenHistory: () => void;
  onOpenExercise: (name: string) => void;
}) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [order, setOrder] = useState<CardId[]>([...CARD_IDS]);
  const [editing, setEditing] = useState(false);
  const { sharePr, shareNode } = usePrShare();

  useEffect(() => {
    (async () => {
      try {
        const saved = await SecureStore.getItemAsync(ORDER_KEY);
        if (saved) {
          const parsed = JSON.parse(saved) as string[];
          const valid = parsed.filter((id): id is CardId => (CARD_IDS as readonly string[]).includes(id));
          const missing = CARD_IDS.filter((id) => !valid.includes(id));
          if (valid.length > 0) setOrder([...valid, ...missing]);
        }
      } catch {
        // Unreadable preference — fall back to the default order.
      }
    })();
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSummary(await AnalyticsApi.summary());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load your progress");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  /** Swap a card up/down in edit mode and persist the new order. */
  function move(id: CardId, dir: -1 | 1) {
    setOrder((prev) => {
      const i = prev.indexOf(id);
      const j = i + dir;
      if (i < 0 || j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[i], next[j]] = [next[j], next[i]];
      SecureStore.setItemAsync(ORDER_KEY, JSON.stringify(next)).catch(() => {});
      return next;
    });
  }

  const hasData =
    summary != null &&
    (summary.consistency.weeks.some((w) => w.count > 0) || summary.recent_prs.length > 0);

  return (
    <ScreenBackground showHome={false}>
      <ScrollView contentContainerStyle={styles.container}>
        <View style={styles.headerRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.title} maxFontSizeMultiplier={1.2}>
              Progress
            </Text>
          </View>
          {hasData && (
            <Pressable onPress={() => setEditing((e) => !e)} style={styles.editBtn} accessibilityRole="button">
              <Text style={[styles.editText, editing && { color: theme.colors.accent }]}>
                {editing ? "Done" : "Edit"}
              </Text>
            </Pressable>
          )}
        </View>

        {loading ? (
          <View style={styles.center}>
            <ActivityIndicator size="large" color={theme.colors.text} />
          </View>
        ) : error ? (
          <Card>
            <Text style={styles.body}>{error}</Text>
            <Button title="Try again" onPress={load} variant="ghost" size="medium" />
          </Card>
        ) : !hasData ? (
          <Card>
            <Text style={styles.cardTitle}>Nothing to chart yet</Text>
            <Text style={[styles.body, { marginTop: 6 }]}>
              Finish your first workout and this screen starts filling in — consistency, volume,
              PRs, the lot. One session is all it takes.
            </Text>
          </Card>
        ) : (
          <>
            {order.map((id, idx) => (
              <View key={id}>
                {editing && (
                  <View style={styles.reorderRow}>
                    <Text style={styles.reorderLabel}>{CARD_TITLES[id]}</Text>
                    <View style={{ flexDirection: "row", gap: 8 }}>
                      <ArrowBtn dir="up" disabled={idx === 0} onPress={() => move(id, -1)} theme={theme} />
                      <ArrowBtn dir="down" disabled={idx === order.length - 1} onPress={() => move(id, 1)} theme={theme} />
                    </View>
                  </View>
                )}
                {id === "consistency" && <ConsistencyCard s={summary!} theme={theme} styles={styles} />}
                {id === "volume" && <VolumeCard s={summary!} theme={theme} styles={styles} />}
                {id === "prs" && (
                  <PrsCard s={summary!} theme={theme} styles={styles} onOpenExercise={onOpenExercise} onShare={sharePr} />
                )}
                {id === "improved" && (
                  <ImprovedCard s={summary!} theme={theme} styles={styles} onOpenExercise={onOpenExercise} />
                )}
                {id === "muscles" && <MusclesCard s={summary!} theme={theme} styles={styles} />}
              </View>
            ))}

            <NavRow title="Exercise trends" caption="Any lift, charted over time" onPress={onOpenTrends} theme={theme} styles={styles} />
            <NavRow title="History" caption="Calendar heatmap and every past workout" onPress={onOpenHistory} theme={theme} styles={styles} />
          </>
        )}
      </ScrollView>
      {shareNode}
    </ScreenBackground>
  );
}

function ArrowBtn({ dir, disabled, onPress, theme }: { dir: "up" | "down"; disabled: boolean; onPress: () => void; theme: Theme }) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={`Move card ${dir}`}
      style={{
        width: 34,
        height: 34,
        borderRadius: 17,
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: theme.colors.backgroundElevated2,
        opacity: disabled ? 0.35 : 1,
      }}
    >
      <Text style={{ color: theme.colors.text, fontSize: 16, fontWeight: "700" }}>{dir === "up" ? "↑" : "↓"}</Text>
    </Pressable>
  );
}

function ConsistencyCard({ s, theme, styles }: CardProps) {
  const c = s.consistency;
  const onTrack = c.this_week >= c.target_per_week;
  const win =
    c.streak_weeks >= 2
      ? `${c.streak_weeks}-week streak — keep it rolling.`
      : onTrack
        ? "Target hit this week. That's how it's done."
        : c.this_week > 0
          ? `${c.target_per_week - c.this_week} more to hit your week.`
          : "This week's still wide open.";
  return (
    <Card>
      <Text style={styles.cardTitle}>Consistency</Text>
      <View style={styles.statRow}>
        <Stat label="this week" value={`${c.this_week}/${c.target_per_week}`} color={onTrack ? theme.colors.success : theme.colors.text} styles={styles} />
        <Stat label="week streak" value={String(c.streak_weeks)} color={c.streak_weeks > 0 ? theme.colors.accent : theme.colors.text} styles={styles} />
      </View>
      <WeeklyBars
        bars={s.consistency.weeks.map((w, i) => ({
          label: new Date(w.week_start + "T12:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" }),
          value: w.count,
          highlight: i === s.consistency.weeks.length - 1,
        }))}
        maxValue={c.target_per_week}
        height={56}
        showLabels
      />
      {/* Shaded weekly badges: fill deepens with completion; full weeks glow
          as "unlocked" (gamification spec, item 4). Newest on the right. */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ gap: 10, paddingVertical: 10, paddingHorizontal: 2 }}
        style={{ marginTop: 4 }}
      >
        {s.consistency.weeks.slice(-8).map((w, i, arr) => (
          <WeeklyBadge
            key={w.week_start}
            label={new Date(w.week_start + "T12:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" })}
            completed={w.count}
            target={c.target_per_week}
            pct={c.target_per_week > 0 ? Math.round(100 * Math.min(1, w.count / c.target_per_week)) : 0}
            current={i === arr.length - 1}
          />
        ))}
      </ScrollView>
      <Text style={styles.win}>{win}</Text>
    </Card>
  );
}

function VolumeCard({ s, theme, styles }: CardProps) {
  const v = s.volume;
  const up = (v.pct_change ?? 0) >= 0;
  return (
    <Card>
      <Text style={styles.cardTitle}>Volume</Text>
      <View style={styles.statRow}>
        <Stat label="this month" value={fmt(v.this_month)} color={theme.colors.text} styles={styles} />
        <Stat label="last month" value={fmt(v.last_month)} color={theme.colors.textSecondary} styles={styles} />
        {v.pct_change != null && (
          <Stat
            label="change"
            value={`${up ? "+" : ""}${v.pct_change}%`}
            color={up ? theme.colors.success : theme.colors.danger}
            styles={styles}
          />
        )}
      </View>
      <Text style={styles.caption}>Total load moved (weight × reps), calendar month.</Text>
    </Card>
  );
}

function PrsCard({
  s,
  theme,
  styles,
  onOpenExercise,
  onShare,
}: CardProps & {
  onOpenExercise: (n: string) => void;
  onShare: (pr: { exercise: string; value: number; previous: number; date: string }) => void;
}) {
  return (
    <Card>
      <Text style={styles.cardTitle}>Recent PRs</Text>
      {s.recent_prs.length === 0 ? (
        <Text style={[styles.body, { marginTop: 6 }]}>
          No new PRs in the last 30 days. They're coming — the trend charts will tell you which lift is closest.
        </Text>
      ) : (
        s.recent_prs.map((p, i) => (
          <Pressable key={i} onPress={() => onOpenExercise(p.exercise)} style={styles.listRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowTitle} numberOfLines={1}>{p.exercise}</Text>
              <Text style={styles.caption}>
                est. 1RM {p.previous} → <Text style={{ color: theme.colors.success, fontWeight: "700" }}>{p.value}</Text>
                {"  ·  "}
                {new Date(p.date + "T12:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" })}
              </Text>
            </View>
            <Pressable
              onPress={() => onShare({ exercise: p.exercise, value: p.value, previous: p.previous, date: p.date })}
              hitSlop={8}
              accessibilityLabel={`Share ${p.exercise} PR`}
              style={{
                paddingVertical: 4,
                paddingHorizontal: 10,
                borderRadius: theme.radius.pill,
                backgroundColor: theme.colors.backgroundElevated2,
                marginRight: 10,
              }}
            >
              <Text style={{ fontSize: 12, fontWeight: "700", color: theme.colors.accent }}>Share</Text>
            </Pressable>
            <ChevronGlyph color={theme.colors.textTertiary} />
          </Pressable>
        ))
      )}
    </Card>
  );
}

function ImprovedCard({ s, theme, styles, onOpenExercise }: CardProps & { onOpenExercise: (n: string) => void }) {
  return (
    <Card>
      <Text style={styles.cardTitle}>Most improved</Text>
      {s.most_improved.length === 0 ? (
        <Text style={[styles.body, { marginTop: 6 }]}>
          Needs about four sessions per lift over 90 days to rank improvements. Keep logging.
        </Text>
      ) : (
        s.most_improved.map((m, i) => (
          <Pressable key={i} onPress={() => onOpenExercise(m.exercise)} style={styles.listRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowTitle} numberOfLines={1}>{m.exercise}</Text>
              <Text style={styles.caption}>{m.sessions} sessions · last 90 days</Text>
            </View>
            <Text style={{ color: theme.colors.success, fontWeight: "800", fontSize: 16 }}>+{m.pct}%</Text>
          </Pressable>
        ))
      )}
    </Card>
  );
}

function MusclesCard({ s, theme, styles }: CardProps) {
  const palette = musclePalette(theme);
  const slices = s.muscle_focus.map((m, i) => ({
    label: prettyMuscle(m.muscle),
    value: m.volume,
    color: palette[i % palette.length],
  }));
  return (
    <Card>
      <Text style={styles.cardTitle}>Muscle focus</Text>
      <Text style={[styles.caption, { marginBottom: 10 }]}>Where your volume went, last 30 days.</Text>
      <Donut slices={slices} centerLabel={s.muscle_focus.length > 0 ? `${s.muscle_focus.length}` : undefined} centerSub="groups" />
    </Card>
  );
}

type CardProps = { s: AnalyticsSummary; theme: Theme; styles: ReturnType<typeof getStyles> };

function Stat({ label, value, color, styles }: { label: string; value: string; color: string; styles: ReturnType<typeof getStyles> }) {
  return (
    <View style={{ marginRight: 24 }}>
      <Text style={[styles.statValue, { color }]} maxFontSizeMultiplier={1.3}>{value}</Text>
      <Text style={styles.caption}>{label}</Text>
    </View>
  );
}

function NavRow({ title, caption, onPress, theme, styles }: { title: string; caption: string; onPress: () => void; theme: Theme; styles: ReturnType<typeof getStyles> }) {
  return (
    <Pressable onPress={onPress}>
      <Card>
        <View style={{ flexDirection: "row", alignItems: "center" }}>
          <View style={{ flex: 1 }}>
            <Text style={styles.rowTitle}>{title}</Text>
            <Text style={styles.caption}>{caption}</Text>
          </View>
          <ChevronGlyph color={theme.colors.textTertiary} />
        </View>
      </Card>
    </Pressable>
  );
}

function getStyles(theme: Theme) {
  return StyleSheet.create({
    container: { padding: 20, paddingTop: 8, gap: 14, flexGrow: 1 },
    center: { flex: 1, alignItems: "center", justifyContent: "center", paddingVertical: 60 },
    headerRow: { flexDirection: "row", alignItems: "center", marginBottom: 4 },
    title: { fontSize: 34, fontWeight: "800", color: theme.colors.text, letterSpacing: -0.5 },
    editBtn: { paddingVertical: 6, paddingHorizontal: 10 },
    editText: { fontSize: 15, fontWeight: "600", color: theme.colors.textSecondary },
    cardTitle: { fontSize: 17, fontWeight: "700", color: theme.colors.text, marginBottom: 8 },
    body: { fontSize: 15, color: theme.colors.textSecondary, lineHeight: 21 },
    caption: { fontSize: 12, color: theme.colors.textTertiary, marginTop: 2 },
    statRow: { flexDirection: "row", marginBottom: 12 },
    statValue: { fontSize: 24, fontWeight: "800" },
    win: { fontSize: 13, fontWeight: "600", color: theme.colors.textSecondary, marginTop: 10 },
    listRow: {
      flexDirection: "row",
      alignItems: "center",
      paddingVertical: 8,
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: theme.colors.border,
    },
    rowTitle: { fontSize: 15, fontWeight: "600", color: theme.colors.text },
    reorderRow: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "space-between",
      paddingHorizontal: 4,
      paddingBottom: 6,
    },
    reorderLabel: { fontSize: 13, fontWeight: "700", color: theme.colors.accent, letterSpacing: 0.3 },
  });
}
