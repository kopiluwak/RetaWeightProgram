// Add-your-own-exercise: two ways to add a movement to the active program.
//   1. "Pick a specific one" — search the known library (pull-up, push-up,
//      isolation curl, …) and tap Add; the server files it on the right day.
//   2. "Saw it on social media" — type what you saw; the server classifies the
//      muscle group + writes a form cue and suggests the day (you can override).
// Either way the exercise lands on the correct muscle-group day and is loggable.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import {
  AddExercisePayload,
  ClassifiedExercise,
  ExerciseLibraryItem,
  Program,
  ProgramApi,
} from "../api";
import { Theme, useTheme } from "../theme";
import { Badge, Button, Card, Chip, ScreenBackground } from "../ui";

type Mode = "library" | "social";

/** onDone fires after a successful add so the shell can refresh + return. */
export default function AddExerciseScreen({
  program,
  onDone,
  onBack,
}: {
  program: Program;
  onDone: () => void;
  onBack: () => void;
}) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const [mode, setMode] = useState<Mode>("library");
  const dayNames = useMemo(() => program.days.map((d) => d.name), [program]);

  // --- shared submit ---
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  async function submitAdd(payload: AddExercisePayload, landedDay: string) {
    setError(null);
    setBusy(true);
    try {
      await ProgramApi.addExercise(payload);
      setOkMsg(`Added to ${landedDay}.`);
      setTimeout(onDone, 650); // let the confirmation register, then return
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add exercise");
      setBusy(false);
    }
  }

  return (
    <ScreenBackground onBack={busy ? undefined : onBack} backLabel="Program">
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Text style={styles.title} maxFontSizeMultiplier={1.3}>Add an exercise</Text>
        <Text style={styles.subtitle} maxFontSizeMultiplier={1.6}>
          It’ll be placed on the matching muscle-group day and show up in your workout logger.
        </Text>

        <View style={styles.modeRow}>
          <Chip label="Pick a specific one" selected={mode === "library"} onPress={() => { setMode("library"); setError(null); }} disabled={busy} />
          <Chip label="Saw it on social media" selected={mode === "social"} onPress={() => { setMode("social"); setError(null); }} disabled={busy} />
        </View>

        {error ? <Text style={styles.error}>{error}</Text> : null}
        {okMsg ? <Text style={styles.ok}>{okMsg}</Text> : null}

        {mode === "library" ? (
          <LibraryPicker dayNames={dayNames} busy={busy} onAdd={submitAdd} />
        ) : (
          <SocialSuggest dayNames={dayNames} busy={busy} onAdd={submitAdd} />
        )}
      </ScrollView>
    </ScreenBackground>
  );
}

// ---------------------------------------------------------------------------
// Mode 1: pick a known exercise
// ---------------------------------------------------------------------------
function LibraryPicker({
  dayNames,
  busy,
  onAdd,
}: {
  dayNames: string[];
  busy: boolean;
  onAdd: (p: AddExercisePayload, day: string) => void;
}) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const [items, setItems] = useState<ExerciseLibraryItem[] | null>(null);
  const [query, setQuery] = useState("");
  const [muscle, setMuscle] = useState<string | null>(null);

  useEffect(() => {
    ProgramApi.exerciseLibrary().then(setItems).catch(() => setItems([]));
  }, []);

  // Chip list keys off each exercise's MAIN mover (primary[0]) so filtering a
  // body part only surfaces movements that TRAIN it as the primary muscle — not
  // compounds where it's a secondary (e.g. rows shouldn't appear under "biceps").
  const muscles = useMemo(() => {
    const s = new Set<string>();
    (items ?? []).forEach((it) => { if (it.primary[0]) s.add(it.primary[0]); });
    return Array.from(s).sort();
  }, [items]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (items ?? []).filter((it) => {
      const okM = !muscle || it.primary[0] === muscle;   // primary mover only
      const okQ = !q || it.name.toLowerCase().includes(q) || it.primary.some((m) => m.includes(q));
      return okM && okQ;
    });
  }, [items, query, muscle]);

  if (items === null) {
    return <ActivityIndicator style={{ marginTop: 24 }} color={theme.colors.text} />;
  }

  return (
    <View>
      <TextInput
        style={styles.input}
        placeholder="Search (e.g. curl, pull, squat)"
        placeholderTextColor={theme.colors.textTertiary}
        value={query}
        onChangeText={setQuery}
        autoCorrect={false}
        editable={!busy}
      />
      <View style={styles.filterRow}>
        <Chip label="All" selected={muscle === null} onPress={() => setMuscle(null)} disabled={busy} />
        {muscles.map((m) => (
          <Chip key={m} label={m} selected={muscle === m} onPress={() => setMuscle(m)} disabled={busy} />
        ))}
      </View>

      {filtered.map((it) => (
        <Card key={it.id} style={styles.exCard}>
          <View style={styles.exRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.exName} maxFontSizeMultiplier={1.3}>{it.name}</Text>
              <Text style={styles.exMeta} maxFontSizeMultiplier={1.6}>
                {it.primary.join(", ")}{it.compound ? " · compound" : ""}
              </Text>
            </View>
            <Button
              title="Add"
              onPress={() => onAdd({ library_id: it.id }, dayNameFor(dayNames, it.primary))}
              variant="secondary"
              size="small"
              fullWidth={false}
              disabled={busy}
            />
          </View>
        </Card>
      ))}
      {filtered.length === 0 ? <Text style={styles.empty}>No matches.</Text> : null}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Mode 2: describe something you saw
// ---------------------------------------------------------------------------
function SocialSuggest({
  dayNames,
  busy,
  onAdd,
}: {
  dayNames: string[];
  busy: boolean;
  onAdd: (p: AddExercisePayload, day: string) => void;
}) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const [text, setText] = useState("");
  const [classifying, setClassifying] = useState(false);
  const [result, setResult] = useState<ClassifiedExercise | null>(null);
  const [dayIndex, setDayIndex] = useState<number>(0);
  const [err, setErr] = useState<string | null>(null);

  const classify = useCallback(async () => {
    if (!text.trim()) return;
    setErr(null);
    setClassifying(true);
    setResult(null);
    try {
      const r = await ProgramApi.classifyExercise(text.trim());
      setResult(r);
      setDayIndex(r.suggested_day_index);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not read that exercise");
    } finally {
      setClassifying(false);
    }
  }, [text]);

  return (
    <View>
      <TextInput
        style={[styles.input, styles.inputTall]}
        placeholder="Describe it — e.g. “that cable pushdown thing I saw on TikTok”"
        placeholderTextColor={theme.colors.textTertiary}
        value={text}
        onChangeText={setText}
        multiline
        editable={!busy && !classifying}
      />
      <Button
        title={classifying ? "Reading…" : "Identify exercise"}
        onPress={classify}
        variant="secondary"
        size="medium"
        loading={classifying}
        disabled={busy || classifying || !text.trim()}
      />
      {err ? <Text style={styles.error}>{err}</Text> : null}

      {result ? (
        <Card style={styles.resultCard} accentColor={theme.colors.accent}>
          <Text style={styles.exName} maxFontSizeMultiplier={1.3}>{result.name}</Text>
          <View style={styles.badges}>
            {result.primary.map((m) => <Badge key={m} label={m} tone="neutral" />)}
            {result.compound ? <Badge label="compound" tone="neutral" /> : null}
            {result.source === "library" ? <Badge label="known move" tone="success" /> : null}
          </View>
          {result.description ? <Text style={styles.exDesc} maxFontSizeMultiplier={1.7}>{result.description}</Text> : null}

          <Text style={styles.dayLabel}>Add to which day?</Text>
          <View style={styles.filterRow}>
            {dayNames.map((n, i) => (
              <Chip key={n} label={`Day ${i + 1}`} selected={i === dayIndex} onPress={() => setDayIndex(i)} disabled={busy} />
            ))}
          </View>
          <Text style={styles.dayName} maxFontSizeMultiplier={1.6}>{dayNames[dayIndex]}</Text>

          <View style={{ marginTop: 12 }}>
            <Button
              title="Add to my program"
              onPress={() => onAdd({
                name: result.name,
                primary: result.primary,
                compound: result.compound,
                description: result.description,
                day_index: dayIndex,
              }, dayNames[dayIndex])}
              variant="primary"
              disabled={busy}
            />
          </View>
        </Card>
      ) : null}
    </View>
  );
}

/** Local mirror of the server's day-name hint, just for the Add button label. */
function dayNameFor(dayNames: string[], primary: string[]): string {
  const KW: Record<string, string[]> = {
    chest: ["push", "chest"], triceps: ["push", "arms", "tricep"], shoulders: ["shoulder", "push"],
    back: ["pull", "back"], biceps: ["pull", "arms", "bicep"],
    quads: ["legs", "quad"], hamstrings: ["legs", "hamstring"], glutes: ["legs", "glute"],
    calves: ["legs", "calf", "calv"], core: ["pull", "legs", "core", "abs"],
  };
  for (const m of primary) {
    const hit = dayNames.findIndex((n) => (KW[m] ?? []).some((kw) => n.toLowerCase().includes(kw)));
    if (hit >= 0) return dayNames[hit];
  }
  return dayNames[0] ?? "your program";
}

function getStyles(theme: Theme) {
  return StyleSheet.create({
    container: { padding: 20, gap: 10, paddingBottom: 48 },
    title: { fontSize: 26, fontWeight: "700", color: theme.colors.text, marginTop: 8 },
    subtitle: { fontSize: 14, color: theme.colors.textSecondary, lineHeight: 20 },
    modeRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 8 },
    error: { color: theme.colors.danger, fontWeight: "600", marginTop: 6 },
    ok: { color: theme.colors.success, fontWeight: "700", marginTop: 6 },
    input: {
      borderWidth: 1, borderColor: theme.colors.border, borderRadius: 10,
      paddingHorizontal: 12, paddingVertical: 10, fontSize: 15,
      color: theme.colors.text, backgroundColor: theme.colors.backgroundElevated2, marginTop: 10,
    },
    inputTall: { minHeight: 76, textAlignVertical: "top" },
    filterRow: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 10 },
    exCard: { marginTop: 10 },
    exRow: { flexDirection: "row", alignItems: "center", gap: 10 },
    exName: { fontSize: 16, fontWeight: "700", color: theme.colors.text },
    exMeta: { fontSize: 12, color: theme.colors.textSecondary, marginTop: 2 },
    exDesc: { fontSize: 13, color: theme.colors.textSecondary, marginTop: 10, lineHeight: 18 },
    empty: { color: theme.colors.textTertiary, marginTop: 16, textAlign: "center" },
    resultCard: { marginTop: 14, gap: 4 },
    badges: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 },
    dayLabel: { fontSize: 13, fontWeight: "700", color: theme.colors.text, marginTop: 14 },
    dayName: { fontSize: 13, color: theme.colors.textSecondary, marginTop: 6 },
  });
}
