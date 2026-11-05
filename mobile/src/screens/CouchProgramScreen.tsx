// Couch-to-Weights beginner view: the same 3/4/5-day split, but each day shows
// only the exercises unlocked so far. Starts at one move per day and adds one
// each week via an explicit "Add it / Not yet" card. See COUCH_TO_WEIGHTS_SPEC.md.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Alert, Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { CouchApi, CouchView, Program, ProgramApi } from "../api";
import { friendlyError } from "../errors";
import { DAY_OPTIONS, dayShortLabel } from "../labels";
import { nextDayIndex } from "../programDays";
import { Theme, useTheme } from "../theme";
import { Badge, Button, Card, Chip, ProgressBar, ScreenBackground } from "../ui";

/**
 * Beginner program home. Reuses the workout logger by handing it a program that
 * carries the real program id but only the revealed exercises for the chosen day.
 */
export default function CouchProgramScreen({
  onBack,
  onStartWorkout,
  onGraduate,
  onStateChanged,
  onCustomize,
  onAddEquipment,
  onAddExercise,
  habitDays,
}: {
  onBack: () => void;
  onStartWorkout: (program: Program, dayIndex: number) => void;
  onGraduate: () => void;          // route to the full ProgramScreen
  onStateChanged?: () => void;     // let the shell refresh /me (updates the ramp badge)
  onCustomize?: () => void;        // open the equipment customization screen
  onAddEquipment?: () => void;     // open the "add via scan" capture flow
  onAddExercise?: (program: Program) => void;  // open the add-exercise screen
  habitDays?: number;              // days/week from onboarding — pre-fills the split picker
}) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const [view, setView] = useState<CouchView | null>(null);
  const [program, setProgram] = useState<Program | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsProgram, setNeedsProgram] = useState(false);
  const [activeDay, setActiveDay] = useState(0);
  // The beginner's own days-per-week choice on the first-run build screen.
  // Seeded from onboarding, but editable here — beginners never reach
  // ProgramScreen, where the split picker used to live exclusively.
  const [buildDays, setBuildDays] = useState<number>(
    habitDays && DAY_OPTIONS.includes(habitDays) ? habitDays : 3,
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // The workout logger needs the real program (id + metadata); the couch view
      // supplies the revealed day slices we actually show and log.
      const v = await CouchApi.get();
      const p = await ProgramApi.current();
      setView(v);
      setProgram(p);
      setNeedsProgram(false);
      // Land on the day AFTER the most recently completed session — finishing
      // a workout returns here, and reopening on Day 1 every time made the
      // beginner look stuck on their first day. Same rule as ProgramScreen;
      // best-effort, so null just clamps the existing selection.
      const next = await nextDayIndex(v.days);
      setActiveDay((d) => (next !== null ? next : Math.min(d, Math.max(0, v.days.length - 1))));
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Could not load your plan";
      // "No active program yet" is the expected first-run state -> build screen.
      // Anything else is a real error and must be shown, not silently masked.
      if (/generate a program first/i.test(msg)) {
        setNeedsProgram(true);
        setView(null);
        setError(null);
      } else {
        setNeedsProgram(false);
        setView(null);
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Build (or rebuild) the base program, then immediately load the beginner view.
  // Errors from EITHER step surface here rather than bouncing back to the build
  // screen with no explanation.
  async function buildPlan(opts: { bodyweightOnly?: boolean; days?: number } = {}) {
    setBusy(true);
    setError(null);
    try {
      // Always send the day count explicitly: the beginner picks it here, and the
      // backend makes an explicit choice sticky on the habits row.
      await ProgramApi.generate({
        daysPerWeek: opts.days ?? buildDays,
        ...(opts.bodyweightOnly ? { bodyweightOnly: true } : {}),
      });
      const v = await CouchApi.get();
      const p = await ProgramApi.current();
      setView(v);
      setProgram(p);
      setNeedsProgram(false);
      setActiveDay(0);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not build your plan");
    } finally {
      setBusy(false);
    }
  }

  /** Rebuild the plan, optionally switching the 3/4/5-day split. */
  const generate = (days?: number) =>
    buildPlan({ days: days ?? program?.days_per_week ?? buildDays });

  async function decide(action: "add" | "skip") {
    setBusy(true);
    setError(null);
    try {
      const v = await CouchApi.advance(action);
      setView(v);
      setActiveDay((d) => Math.min(d, Math.max(0, v.days.length - 1)));
      onStateChanged?.();
    } catch (e) {
      setError(friendlyError(e, "Could not update your plan"));
    } finally {
      setBusy(false);
    }
  }

  async function restart() {
    setBusy(true);
    setError(null);
    try {
      await CouchApi.restart();
      await load();
      onStateChanged?.();
    } catch (e) {
      setError(friendlyError(e, "Could not restart"));
    } finally {
      setBusy(false);
    }
  }

  async function graduateNow() {
    setBusy(true);
    setError(null);
    try {
      await CouchApi.graduate();
      onGraduate();  // app shows the full program
    } catch (e) {
      setError(friendlyError(e, "Could not graduate"));
    } finally {
      setBusy(false);
    }
  }

  /** Regenerating replaces the current plan, so confirm first. Passing a day
   *  count that differs from the current split reframes the prompt as a switch. */
  function confirmRegenerate(days?: number) {
    const changingSplit = days !== undefined && !!program && days !== program.days_per_week;
    Alert.alert(
      changingSplit ? `Train ${days} days a week?` : "Regenerate program?",
      changingSplit
        ? `This rebuilds your plan as a ${days}-day split. You stay at Week ${view?.week ?? 1} of the ramp and your workout history is kept.`
        : "This rebuilds your plan from your current equipment. Your ramp progress and history are kept.",
      [
        { text: "Cancel", style: "cancel" },
        { text: changingSplit ? "Switch" : "Regenerate", style: "destructive", onPress: () => generate(days) },
      ],
    );
  }
  function confirmGraduate() {
    Alert.alert("Graduate to the full program?", "This skips the beginner ramp and shows every exercise now. You can restart the ramp later.", [
      { text: "Cancel", style: "cancel" },
      { text: "Graduate", onPress: graduateNow },
    ]);
  }
  function confirmRestart() {
    Alert.alert("Restart at Week 1?", "This resets the beginner ramp to one exercise per day. Your workout history is kept.", [
      { text: "Cancel", style: "cancel" },
      { text: "Restart", style: "destructive", onPress: restart },
    ]);
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

  // Beginner hasn't generated a base program yet.
  if (needsProgram) {
    // If the last build failed because there's no equipment on file, guide the
    // user to scan or go bodyweight instead of leaving them on a dead button.
    const noInventory = !!error && /inventory/i.test(error);
    return (
      <ScreenBackground showHome={false}>
        <ScrollView contentContainerStyle={styles.container}>
          <Text style={styles.title} maxFontSizeMultiplier={1.3}>Let's build your plan</Text>
          <Text style={styles.subtitle} maxFontSizeMultiplier={1.6}>
            We'll create your full routine, then ease you in — one exercise per day to start,
            adding one more each week.
          </Text>
          {/* Days per week. Beginners never reach ProgramScreen, so this is the
              only place they can set (or change) their schedule before the
              plan is built. Seeded from onboarding. */}
          <Text style={styles.buildLabel} maxFontSizeMultiplier={1.4}>How many days a week?</Text>
          <View style={styles.chipRow}>
            {DAY_OPTIONS.map((d) => (
              <Chip
                key={d}
                label={`${d} days`}
                selected={d === buildDays}
                onPress={() => setBuildDays(d)}
                disabled={busy}
              />
            ))}
          </View>
          <Text style={styles.buildHint} maxFontSizeMultiplier={1.6}>
            Each day trains a different muscle group. You can change this later.
          </Text>

          {error ? (
            <Card style={styles.errorCard} accentColor={theme.colors.danger}>
              <Text style={styles.error} maxFontSizeMultiplier={1.6}>{error}</Text>
            </Card>
          ) : null}
          <View style={{ marginTop: 16, gap: 10 }}>
            <Button title={`Build my ${buildDays}-day beginner plan`} onPress={() => buildPlan()} loading={busy} disabled={busy} variant="primary" />
            {noInventory && onAddEquipment ? (
              <Button title="Scan my equipment" onPress={onAddEquipment} variant="secondary" disabled={busy} />
            ) : null}
            <Button title="Use bodyweight only" onPress={() => buildPlan({ bodyweightOnly: true })} variant="secondary" disabled={busy} />
          </View>
        </ScrollView>
      </ScreenBackground>
    );
  }

  if (!view || !program) {
    return (
      <ScreenBackground showHome={false}>
        <ScrollView contentContainerStyle={styles.container}>
          <Text style={styles.title}>Your plan</Text>
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <Button title="Retry" onPress={load} variant="secondary" size="medium" />
        </ScrollView>
      </ScreenBackground>
    );
  }

  const progress = view.full > 0 ? view.unlocked / view.full : 0;
  const day = view.days[activeDay];
  // Hand the logger the real program id + metadata but only the revealed exercises.
  const loggableProgram: Program = { ...program, days: view.days };

  return (
    <ScreenBackground showHome={false}>
      <ScrollView contentContainerStyle={styles.container}>
        <View style={styles.headerRow}>
          <Text style={styles.title} maxFontSizeMultiplier={1.3}>Couch-to-Weights</Text>
          <Badge label={`Week ${view.week}`} tone="accent" />
        </View>
        <Text style={styles.headline} maxFontSizeMultiplier={1.4}>{view.headline}</Text>

        <View style={styles.progressWrap}>
          <ProgressBar progress={progress} color={theme.colors.accent} height={10} />
          <Text style={styles.progressLabel} maxFontSizeMultiplier={1.4}>
            {view.unlocked} of {view.full} exercises per day
          </Text>
        </View>

        {/* Warm coach line for the current state. */}
        <Card style={styles.messageCard} accentColor={theme.colors.accent}>
          <Text style={styles.messageText} maxFontSizeMultiplier={1.6}>{view.message}</Text>
        </Card>

        {/* Just-added celebration. */}
        {view.added_today ? (
          <Card style={styles.addedCard} accentColor={theme.colors.success}>
            <Badge label="New this week" tone="success" />
            <Text style={styles.addedText} maxFontSizeMultiplier={1.6}>
              Added {view.added_today}.{view.added_reason ? ` ${view.added_reason}` : ""}
            </Text>
          </Card>
        ) : null}

        {/* The weekly level-up decision. */}
        {view.decision_due ? (
          <Card style={styles.decisionCard} accentColor={theme.colors.accent}>
            <Text style={styles.decisionTitle} maxFontSizeMultiplier={1.4}>Ready to level up?</Text>
            <View style={styles.decisionButtons}>
              <View style={{ flex: 1 }}>
                <Button title="Add it" onPress={() => decide("add")} loading={busy} disabled={busy} variant="success" />
              </View>
              <View style={{ flex: 1 }}>
                <Button title="Not yet" onPress={() => decide("skip")} disabled={busy} variant="secondary" />
              </View>
            </View>
          </Card>
        ) : null}

        {/* Graduation handoff. */}
        {view.graduated ? (
          <View style={{ marginTop: 16 }}>
            <Button title="Go to my full program" onPress={onGraduate} variant="primary" />
          </View>
        ) : null}

        {error ? <Text style={styles.error}>{error}</Text> : null}

        {/* Day picker (same shape as the full program, fewer exercises).
            Labelled by muscle group, not "Day 1/2/3" — this is how the user
            says "not legs today, I want arms". Days are independent, so
            training them out of order costs nothing. */}
        <Text style={styles.sectionTitle} maxFontSizeMultiplier={1.3}>Today's workout</Text>
        <Text style={styles.sectionHint} maxFontSizeMultiplier={1.6}>
          Not feeling this one? Tap any muscle group — you can train your days in any order.
        </Text>
        <View style={styles.tabs}>
          {view.days.map((d, i) => (
            <Chip
              key={`${d.name}-${i}`}
              label={dayShortLabel(d.name, i)}
              selected={i === activeDay}
              onPress={() => setActiveDay(i)}
            />
          ))}
        </View>

        <Text style={styles.dayName} maxFontSizeMultiplier={1.3}>{day.name}</Text>
        <Text style={styles.dayMeta}>Day {activeDay + 1} · ~{day.est_minutes} min · {day.exercises.length} exercise{day.exercises.length === 1 ? "" : "s"}</Text>

        <View style={{ marginTop: 12 }}>
          <Button title="Log this workout" onPress={() => onStartWorkout(loggableProgram, activeDay)} variant="success" />
        </View>

        {day.exercises.map((e, i) => (
          <Card key={`${e.name}-${i}`} style={styles.exCard}>
            <View style={styles.exHeader}>
              <View style={{ flex: 1 }}>
                <Text style={styles.exName} maxFontSizeMultiplier={1.3}>{e.name}</Text>
                <Text style={styles.exMeta} maxFontSizeMultiplier={1.6}>{e.primary.join(", ")}</Text>
              </View>
              <View style={styles.exPrescription}>
                <Text style={styles.exSets} maxFontSizeMultiplier={1.3}>{e.sets} × {e.reps}</Text>
                <Badge label={`RIR ${e.rir}`} tone="neutral" />
              </View>
            </View>
            {e.description ? <Text style={styles.exDesc} maxFontSizeMultiplier={1.7}>{e.description}</Text> : null}
            {e.video_url ? (
              <Pressable onPress={() => Linking.openURL(e.video_url)}>
                <Text style={styles.exVideo}>▶ Watch how-to</Text>
              </Pressable>
            ) : null}
          </Card>
        ))}

        <Card style={styles.manage}>
          <Text style={styles.manageTitle} maxFontSizeMultiplier={1.3}>Manage program</Text>

          {/* Days per week, after the plan exists. Mirrors ProgramScreen's
              split picker, which beginners can't reach. */}
          <Text style={styles.manageLabel} maxFontSizeMultiplier={1.4}>Days per week</Text>
          <View style={styles.chipRow}>
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
            Changing this rebuilds your plan. You keep your ramp week and history.
          </Text>

          <Button title="Regenerate program" onPress={() => confirmRegenerate()} variant="secondary" size="medium" loading={busy} disabled={busy} />
          {onAddExercise ? <Button title="Add an exercise" onPress={() => onAddExercise(program)} variant="secondary" size="medium" disabled={busy} /> : null}
          {onCustomize ? <Button title="Customize equipment" onPress={onCustomize} variant="secondary" size="medium" disabled={busy} /> : null}
          {onAddEquipment ? <Button title="Add equipment (scan)" onPress={onAddEquipment} variant="secondary" size="medium" disabled={busy} /> : null}
          <Button title="Graduate to full program" onPress={confirmGraduate} variant="secondary" size="medium" disabled={busy} />
          <Button title="Restart at Week 1" onPress={confirmRestart} variant="ghost" size="medium" disabled={busy} />
        </Card>
      </ScrollView>
    </ScreenBackground>
  );
}

function getStyles(theme: Theme) {
  return StyleSheet.create({
    center: { flex: 1, alignItems: "center", justifyContent: "center" },
    container: { padding: 20, gap: 10, paddingBottom: 40 },
    headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 8 },
    title: { fontSize: 26, fontWeight: "700", color: theme.colors.text },
    subtitle: { fontSize: 14, color: theme.colors.textSecondary, lineHeight: 19 },
    headline: { fontSize: 15, fontWeight: "700", color: theme.colors.accent, marginTop: 2 },
    progressWrap: { marginTop: 8, gap: 6 },
    progressLabel: { fontSize: 12, color: theme.colors.textSecondary },
    messageCard: { marginTop: 12 },
    messageText: { fontSize: 14, color: theme.colors.text, lineHeight: 20 },
    addedCard: { marginTop: 10, gap: 8, alignItems: "flex-start" },
    addedText: { fontSize: 13, color: theme.colors.text, lineHeight: 18 },
    decisionCard: { marginTop: 10 },
    decisionTitle: { fontSize: 15, fontWeight: "700", color: theme.colors.text, marginBottom: 10 },
    decisionButtons: { flexDirection: "row", gap: 10 },
    tabs: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 10 },
    chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 8 },
    sectionTitle: { fontSize: 17, fontWeight: "700", color: theme.colors.text, marginTop: 20 },
    sectionHint: { fontSize: 13, color: theme.colors.textSecondary, marginTop: 4, lineHeight: 18 },
    buildLabel: { fontSize: 15, fontWeight: "700", color: theme.colors.text, marginTop: 20 },
    buildHint: { fontSize: 12, color: theme.colors.textTertiary, marginTop: 8, lineHeight: 17 },
    dayName: { fontSize: 19, fontWeight: "700", color: theme.colors.text, marginTop: 14 },
    dayMeta: { fontSize: 12, color: theme.colors.textTertiary },
    exCard: { marginTop: 10 },
    exHeader: { flexDirection: "row", alignItems: "flex-start" },
    exName: { fontSize: 16, fontWeight: "700", color: theme.colors.text },
    exMeta: { fontSize: 12, color: theme.colors.textSecondary, marginTop: 2 },
    exPrescription: { alignItems: "flex-end", gap: 4 },
    exSets: { fontSize: 15, fontWeight: "700", color: theme.colors.text },
    exDesc: { fontSize: 13, color: theme.colors.textSecondary, marginTop: 10, lineHeight: 18 },
    exVideo: { fontSize: 13, color: theme.colors.accent, fontWeight: "600", marginTop: 8 },
    error: { color: theme.colors.danger, fontWeight: "600" },
    errorCard: { marginTop: 12 },
    manage: { marginTop: 22, gap: 10 },
    manageTitle: { fontSize: 15, fontWeight: "700", color: theme.colors.text },
    manageLabel: { fontSize: 13, fontWeight: "700", color: theme.colors.textSecondary, marginTop: 2 },
    manageHint: { fontSize: 12, color: theme.colors.textTertiary, marginTop: -2, marginBottom: 2, lineHeight: 17 },
  });
}
