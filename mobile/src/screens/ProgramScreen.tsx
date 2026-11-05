// Program view: shows the active program day-by-day (prescriptions, form
// cues, video links, gaps, coaching notes), flags staleness after equipment
// edits, and lets the user regenerate or switch the 3/4/5-day split.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Alert, Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { CouchApi, GamificationApi, GamificationSummary, Program, ProgramApi } from "../api";
import { friendlyError } from "../errors";
import { DAY_OPTIONS, dayShortLabel, prettyExperience } from "../labels";
import { nextDayIndex } from "../programDays";
import { Theme, useTheme } from "../theme";
import { Badge, Button, Card, Chip, ScreenBackground, WeeklyChallengeCard } from "../ui";

/** Active-program browser; onStartWorkout(program, dayIndex) opens the logger. */
export default function ProgramScreen({
  onBack,
  onStartWorkout,
  onCustomize,
  onAddEquipment,
  onAddExercise,
  onModeChanged,
}: {
  onBack: () => void;
  onStartWorkout: (program: Program, dayIndex: number) => void;
  onCustomize?: () => void;       // open the equipment customization screen
  onAddEquipment?: () => void;    // open the "add via scan" capture flow
  onAddExercise?: (program: Program) => void;  // open the add-exercise screen
  onModeChanged?: () => void;     // ask the app shell to re-evaluate mode (restart)
}) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const [program, setProgram] = useState<Program | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeDay, setActiveDay] = useState(0);
  const [gami, setGami] = useState<GamificationSummary | null>(null);

  const loadCurrent = useCallback(async () => {
    setLoading(true);
    try {
      const p = await ProgramApi.current();
      setProgram(p);
      // Land on the day AFTER the most recently completed one so returning
      // users pick up where they left off instead of always seeing Day 1.
      // Best-effort (see programDays.ts): null leaves the current selection.
      if (p && p.days.length > 0) {
        const next = await nextDayIndex(p.days);
        if (next !== null) setActiveDay(next);
      }
    } catch {
      setProgram(null);
    } finally {
      setLoading(false);
    }
    // Non-blocking: the challenge card just stays hidden if this fails.
    GamificationApi.summary().then(setGami).catch(() => setGami(null));
  }, []);

  useEffect(() => {
    loadCurrent();
  }, [loadCurrent]);

  async function generate(days?: number) {
    setError(null);
    setBusy(true);
    try {
      const p = await ProgramApi.generate({ daysPerWeek: days });
      setProgram(p);
      setActiveDay(0);
    } catch (e) {
      setError(friendlyError(e, "Could not generate program"));
    } finally {
      setBusy(false);
    }
  }

  /** Regenerating replaces the current program, so confirm first. */
  function confirmRegenerate(days?: number) {
    const changingSplit = days !== undefined && !!program && days !== program.days_per_week;
    Alert.alert(
      changingSplit ? `Switch to a ${days}-day split?` : "Regenerate program?",
      "This replaces your current program with a freshly built one. Your logged workout history is kept.",
      [
        { text: "Cancel", style: "cancel" },
        { text: changingSplit ? "Switch" : "Regenerate", style: "destructive", onPress: () => generate(days) },
      ],
    );
  }

  function confirmRestart() {
    Alert.alert(
      "Restart as beginner?",
      "This resets your program to Week 1 of the beginner ramp (one exercise per day, building up weekly). Your workout history is kept.",
      [
        { text: "Cancel", style: "cancel" },
        { text: "Restart", style: "destructive", onPress: restartBeginner },
      ],
    );
  }

  async function removeExercise(name: string) {
    setError(null);
    setBusy(true);
    try {
      const p = await ProgramApi.removeExercise(activeDay, name);
      setProgram(p);
    } catch (e) {
      setError(friendlyError(e, "Could not remove exercise"));
    } finally {
      setBusy(false);
    }
  }

  async function restartBeginner() {
    setError(null);
    setBusy(true);
    try {
      await CouchApi.restart();
      onModeChanged?.();  // app re-reads /me and switches to the beginner view
    } catch (e) {
      setError(friendlyError(e, "Could not restart"));
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <ScreenBackground showHome={false}>
        <View style={styles.center}>
          <ActivityIndicator size="large" color={theme.colors.text} />
        </View>
      </ScreenBackground>
    );
  }

  // No program yet
  if (!program) {
    return (
      <ScreenBackground showHome={false}>
        <ScrollView contentContainerStyle={styles.container}>
          <Text style={styles.title} maxFontSizeMultiplier={1.3}>Your program</Text>
          <Text style={styles.subtitle} maxFontSizeMultiplier={1.6}>
            Generate a program from your confirmed equipment and training habits.
          </Text>
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <View style={{ marginTop: 16 }}>
            <Button title="Generate my program" onPress={() => generate()} loading={busy} disabled={busy} variant="primary" />
          </View>
        </ScrollView>
      </ScreenBackground>
    );
  }

  const day = program.days[activeDay];

  return (
    <ScreenBackground showHome={false}>
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title} maxFontSizeMultiplier={1.3}>{program.days_per_week}-Day Program</Text>
        <Text style={styles.subtitle} maxFontSizeMultiplier={1.6}>
          {program.session_minutes} min/session · {prettyExperience(program.experience)}
        </Text>

        {gami && <WeeklyChallengeCard summary={gami} />}

        {program.stale ? (
          <Card style={styles.staleBox} accentColor={theme.colors.warning}>
            <Text style={styles.staleText} maxFontSizeMultiplier={1.6}>
              Your equipment changed since this was built. Regenerate to match your current inventory.
            </Text>
            <View style={{ marginTop: 10 }}>
              <Button
                title={busy ? "Regenerating…" : "Regenerate"}
                onPress={() => confirmRegenerate(program.days_per_week)}
                loading={busy}
                disabled={busy}
                variant="secondary"
                size="small"
                fullWidth={false}
              />
            </View>
          </Card>
        ) : null}

        {/* Day picker, labelled by muscle group rather than "Day 1/2/3" — this
            is how the user swaps ("not legs today, I want arms"). Each day
            targets a distinct muscle group, so order within the week is free. */}
        <Text style={styles.sectionTitle} maxFontSizeMultiplier={1.3}>Today's workout</Text>
        <Text style={styles.sectionHint} maxFontSizeMultiplier={1.6}>
          Not feeling this one? Tap any muscle group — you can train your days in any order.
        </Text>
        <View style={styles.tabs}>
          {program.days.map((d, i) => (
            <Chip
              key={`${d.name}-${i}`}
              label={dayShortLabel(d.name, i)}
              selected={i === activeDay}
              onPress={() => setActiveDay(i)}
            />
          ))}
        </View>

        <Text style={styles.dayName} maxFontSizeMultiplier={1.3}>{day.name}</Text>
        <Text style={styles.dayMeta}>Day {activeDay + 1} · ~{day.est_minutes} min</Text>

        <View style={{ marginTop: 12 }}>
          <Button title="Log this workout" onPress={() => onStartWorkout(program, activeDay)} variant="success" />
        </View>

        {day.exercises.map((e, i) => (
          <Card key={`${e.name}-${i}`} style={styles.exCard}>
            <View style={styles.exHeader}>
              <View style={{ flex: 1 }}>
                <View style={styles.exNameRow}>
                  <Text style={styles.exName} maxFontSizeMultiplier={1.3}>{e.name}</Text>
                  {e.added_by_user ? <Badge label="added" tone="accent" /> : null}
                </View>
                <Text style={styles.exMeta} maxFontSizeMultiplier={1.6}>
                  {e.primary.join(", ")}
                  {e.substituted_from ? "  · substitute" : ""}
                </Text>
              </View>
              <View style={styles.exPrescription}>
                <Text style={styles.exSets} maxFontSizeMultiplier={1.3}>{e.sets} × {e.reps}</Text>
                <Badge label={`RIR ${e.rir}`} tone="neutral" />
              </View>
            </View>
            {e.description ? <Text style={styles.exDesc} maxFontSizeMultiplier={1.7}>{e.description}</Text> : null}
            <View style={styles.exFooter}>
              {e.video_url ? (
                <Pressable onPress={() => Linking.openURL(e.video_url)}>
                  <Text style={styles.exVideo}>▶ Watch how-to</Text>
                </Pressable>
              ) : <View />}
              {e.added_by_user ? (
                <Pressable onPress={() => removeExercise(e.name)} disabled={busy} hitSlop={8}>
                  <Text style={styles.exRemove}>Remove</Text>
                </Pressable>
              ) : null}
            </View>
          </Card>
        ))}

        {day.gaps.length > 0 ? (
          <Card style={styles.gapBox} accentColor={theme.colors.danger}>
            {day.gaps.map((g, i) => <Text key={i} style={styles.gapText} maxFontSizeMultiplier={1.6}>⚠ {g}</Text>)}
          </Card>
        ) : null}

        <View style={styles.notes}>
          {program.notes.map((n, i) => <Text key={i} style={styles.noteText} maxFontSizeMultiplier={1.7}>• {n}</Text>)}
        </View>

        <Card style={styles.manage}>
          <Text style={styles.manageTitle} maxFontSizeMultiplier={1.3}>Manage program</Text>

          <Text style={styles.manageLabel} maxFontSizeMultiplier={1.4}>Days per week</Text>
          <View style={styles.switchRow}>
            {DAY_OPTIONS.map((d) => (
              <Chip
                key={d}
                label={`${d} days`}
                selected={d === program.days_per_week}
                onPress={() => confirmRegenerate(d)}
                disabled={busy}
              />
            ))}
          </View>
          <Text style={styles.manageHint} maxFontSizeMultiplier={1.6}>
            Changing this rebuilds the program. Your logged history is kept.
          </Text>

          <Button title="Regenerate program" onPress={() => confirmRegenerate(program.days_per_week)} variant="secondary" size="medium" loading={busy} disabled={busy} />
          {onAddExercise ? <Button title="Add an exercise" onPress={() => onAddExercise(program)} variant="secondary" size="medium" disabled={busy} /> : null}
          {onCustomize ? <Button title="Customize equipment" onPress={onCustomize} variant="secondary" size="medium" disabled={busy} /> : null}
          {onAddEquipment ? <Button title="Add equipment (scan)" onPress={onAddEquipment} variant="secondary" size="medium" disabled={busy} /> : null}
          <Button title="Restart as beginner" onPress={confirmRestart} variant="ghost" size="medium" disabled={busy} />
        </Card>
      </ScrollView>
    </ScreenBackground>
  );
}

function getStyles(theme: Theme) {
  return StyleSheet.create({
    center: { flex: 1, alignItems: "center", justifyContent: "center" },
    container: { padding: 20, gap: 10, paddingBottom: 40 },
    title: { fontSize: 26, fontWeight: "700", color: theme.colors.text, marginTop: 8 },
    subtitle: { fontSize: 14, color: theme.colors.textSecondary },
    error: { color: theme.colors.danger, fontWeight: "600" },
    staleBox: { marginTop: 6 },
    staleText: { color: theme.colors.warning, fontSize: 13, lineHeight: 18 },
    switchRow: { flexDirection: "row", gap: 8, marginTop: 10 },
    tabs: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 10 },
    sectionTitle: { fontSize: 17, fontWeight: "700", color: theme.colors.text, marginTop: 18 },
    sectionHint: { fontSize: 13, color: theme.colors.textSecondary, marginTop: 4, lineHeight: 18 },
    dayName: { fontSize: 19, fontWeight: "700", color: theme.colors.text, marginTop: 14 },
    dayMeta: { fontSize: 12, color: theme.colors.textTertiary },
    exCard: { marginTop: 10 },
    exHeader: { flexDirection: "row", alignItems: "flex-start" },
    exNameRow: { flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap" },
    exName: { fontSize: 16, fontWeight: "700", color: theme.colors.text },
    exMeta: { fontSize: 12, color: theme.colors.textSecondary, marginTop: 2 },
    exFooter: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 8 },
    exRemove: { fontSize: 13, color: theme.colors.danger, fontWeight: "600" },
    exPrescription: { alignItems: "flex-end", gap: 4 },
    exSets: { fontSize: 15, fontWeight: "700", color: theme.colors.text },
    exDesc: { fontSize: 13, color: theme.colors.textSecondary, marginTop: 10, lineHeight: 18 },
    exVideo: { fontSize: 13, color: theme.colors.accent, fontWeight: "600" },
    gapBox: { marginTop: 12 },
    gapText: { color: theme.colors.danger, fontSize: 12 },
    notes: { marginTop: 18, gap: 6, paddingHorizontal: 2 },
    noteText: { fontSize: 12, color: theme.colors.textSecondary, lineHeight: 17 },
    manage: { marginTop: 20, gap: 10 },
    manageTitle: { fontSize: 15, fontWeight: "700", color: theme.colors.text },
    manageLabel: { fontSize: 13, fontWeight: "700", color: theme.colors.textSecondary, marginTop: 2 },
    manageHint: { fontSize: 12, color: theme.colors.textTertiary, marginTop: -2, marginBottom: 2 },
  });
}
