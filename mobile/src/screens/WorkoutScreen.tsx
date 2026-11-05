// Workout logger: three phases — readiness check-in (1-5, feeds
// autoregulation), set-by-set logging with rest timer + last-time pre-fills,
// and a done screen with next-time progression suggestions.
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Animated,
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useAudioPlayer, setAudioModeAsync } from "expo-audio";
import * as Haptics from "expo-haptics";
import { GamificationApi, GamificationSummary, Program, ProgramExercise, ProgressionSuggestion, SetLog, WorkoutApi, WorkoutSession } from "../api";
import { friendlyError } from "../errors";
import { RIR_HINT } from "../labels";
import { Theme, useTheme } from "../theme";
import { Badge, Button, Card, ProgressBar, SetDots, Stepper } from "../ui";

type Phase = "readiness" | "logging" | "done";

const READINESS_OPTIONS: { n: number; label: string; icon: string }[] = [
  { n: 1, label: "Wiped", icon: "○" },
  { n: 2, label: "Low", icon: "◔" },
  { n: 3, label: "OK", icon: "◑" },
  { n: 4, label: "Good", icon: "◕" },
  { n: 5, label: "Great", icon: "●" },
];

/** Full session logger for one program day; onDone() returns to the program. */
export default function WorkoutScreen({
  program,
  dayIndex,
  onDone,
}: {
  program: Program;
  dayIndex: number;
  onDone: () => void;
}) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const day = program.days[dayIndex];
  const [phase, setPhase] = useState<Phase>("readiness");
  const [session, setSession] = useState<WorkoutSession | null>(null);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [lastPerf, setLastPerf] = useState<Record<string, { weight: number | null; reps: number; rir: number }>>({});
  const [suggestions, setSuggestions] = useState<ProgressionSuggestion[]>([]);
  const [gami, setGami] = useState<GamificationSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [restLeft, setRestLeft] = useState<number | null>(null);
  const [restTotal, setRestTotal] = useState(1);
  const beep = useAudioPlayer(require("../../assets/beep.wav"));

  useEffect(() => {
    setAudioModeAsync({ playsInSilentMode: true }).catch(() => {});
  }, []);

  /** Rest-over chime + haptic (both best-effort). */
  function playPing() {
    try {
      beep.seekTo(0);
      beep.play();
    } catch {
      /* audio is best-effort */
    }
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
  }

  useEffect(() => {
    if (restLeft === null) return;
    if (restLeft <= 0) {
      playPing();
      setRestLeft(null);
      return;
    }
    const id = setTimeout(() => setRestLeft((r) => (r === null ? null : r - 1)), 1000);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [restLeft]);

  function startRest(seconds: number) {
    setRestTotal(seconds > 0 ? seconds : 90);
    setRestLeft(seconds > 0 ? seconds : 90);
  }

  /** Start the session with the chosen readiness and pre-fetch last-time numbers. */
  async function begin(readiness: number) {
    setBusy(true);
    setError(null);
    try {
      const [s, last] = await Promise.all([
        WorkoutApi.start(dayIndex, readiness, program.id),
        WorkoutApi.lastPerformance().catch(() => ({})),
      ]);
      setSession(s);
      setLastPerf(last);
      setPhase("logging");
    } catch (e) {
      setError(friendlyError(e, "Could not start workout"));
    } finally {
      setBusy(false);
    }
  }

  /** Leaving mid-session loses the unsaved sets — confirm before bailing. */
  function confirmCancel() {
    const logged = Object.values(counts).reduce((a, b) => a + b, 0);
    if (logged === 0) {
      onDone();
      return;
    }
    Alert.alert(
      "Leave this workout?",
      "Your logged sets won't be saved as a completed session.",
      [
        { text: "Keep going", style: "cancel" },
        { text: "Leave", style: "destructive", onPress: onDone },
      ],
    );
  }

  /** Log one set, bump the per-exercise counter, and kick off the rest timer. */
  async function logSet(ex: ProgramExercise, weight: number | null, reps: number, rir: number) {
    if (!session) return;
    const setNumber = (counts[ex.name] ?? 0) + 1;
    try {
      const s = await WorkoutApi.logSet(session.id, {
        exercise_name: ex.name, set_number: setNumber, reps, rir, weight, reps_range: ex.reps,
      });
      setSession(s);
      setCounts((c) => ({ ...c, [ex.name]: setNumber }));
      Keyboard.dismiss();
      startRest(ex.rest_seconds && ex.rest_seconds > 0 ? ex.rest_seconds : 90);
    } catch (e) {
      setError(friendlyError(e, "Could not log set"));
    }
  }

  /** Complete the session and switch to the suggestions screen. */
  async function finish() {
    if (!session) return;
    setBusy(true);
    try {
      const s = await WorkoutApi.finish(session.id);
      setSuggestions(s.suggestions);
      setPhase("done");
      // Refresh XP/achievements after the finish is committed; reading the
      // summary also awards anything newly unlocked. Non-blocking on failure.
      GamificationApi.summary().then(setGami).catch(() => setGami(null));
    } catch (e) {
      setError(friendlyError(e, "Could not finish"));
    } finally {
      setBusy(false);
    }
  }

  // The exercise the user is currently working through: the first one whose
  // target set count hasn't been reached yet. Everything before it is done,
  // everything after it is upcoming.
  const activeIndex = day.exercises.findIndex((ex) => (counts[ex.name] ?? 0) < ex.sets);
  const totalSetsTarget = day.exercises.reduce((sum, ex) => sum + ex.sets, 0);
  const totalSetsLogged = day.exercises.reduce((sum, ex) => sum + Math.min(counts[ex.name] ?? 0, ex.sets), 0);
  const allDone = activeIndex === -1;

  if (phase === "readiness") {
    return (
      <View style={{ flex: 1, backgroundColor: theme.colors.background }}>
        <ScrollView contentContainerStyle={styles.center}>
          <Text style={styles.title} maxFontSizeMultiplier={1.3}>{day.name}</Text>
          <Text style={styles.subtitle} maxFontSizeMultiplier={1.5}>How's your energy today? This tunes how hard to push.</Text>
          <View style={{ gap: 10, marginTop: 16, width: "100%" }}>
            {READINESS_OPTIONS.map((o) => (
              <Pressable key={o.n} disabled={busy} onPress={() => begin(o.n)}>
                <Card style={styles.readinessCard}>
                  <Text style={[styles.readinessIcon, { color: theme.colors.accent }]}>{o.icon}</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.readinessNum} maxFontSizeMultiplier={1.3}>{o.n} — {o.label}</Text>
                  </View>
                  <Text style={[styles.chevron, { color: theme.colors.textTertiary }]}>›</Text>
                </Card>
              </Pressable>
            ))}
          </View>
          {busy ? <ActivityIndicator style={{ marginTop: 16 }} color={theme.colors.text} /> : null}
          {error ? <Text style={styles.error} maxFontSizeMultiplier={1.5}>{error}</Text> : null}
          <Pressable onPress={onDone} style={{ marginTop: 20 }}>
            <Text style={styles.link}>Cancel</Text>
          </Pressable>
        </ScrollView>
      </View>
    );
  }

  if (phase === "done") {
    return (
      <View style={{ flex: 1, backgroundColor: theme.colors.background }}>
        <ScrollView contentContainerStyle={styles.container}>
          <View style={styles.doneBadgeWrap}>
            <Text style={styles.doneCheck}>✓</Text>
          </View>
          <Text style={styles.title} maxFontSizeMultiplier={1.3}>Session logged</Text>

          {/* XP + streak payoff — the reason to come back tomorrow. */}
          {gami && (
            <View style={styles.xpRow}>
              <View style={styles.xpChip}>
                <Text style={styles.xpChipText} maxFontSizeMultiplier={1.2}>
                  +{gami.xp.per_workout} XP
                </Text>
              </View>
              <Text style={styles.xpMeta} maxFontSizeMultiplier={1.4}>
                Level {gami.xp.level} · 🔥 {gami.workout.current_streak}-day streak ·{" "}
                {gami.workout.sessions_this_week}/{gami.workout.target_per_week} this week
              </Text>
            </View>
          )}
          {gami && gami.newly_earned.length > 0 && (
            <View style={styles.unlockBanner}>
              <Text style={styles.unlockText} maxFontSizeMultiplier={1.3}>
                🏆 Achievement unlocked:{" "}
                {gami.newly_earned
                  .map((k) => gami.achievements.find((a) => a.key === k)?.name ?? k)
                  .join(" · ")}
              </Text>
            </View>
          )}

          <Text style={styles.subtitle} maxFontSizeMultiplier={1.5}>Next-time suggestions, based on what you logged:</Text>
          {suggestions.map((s, i) => (
            <Card key={i} style={{ marginTop: 10 }} accentColor={actionColor(s.action, theme)}>
              <View style={styles.sugHeader}>
                <Text style={styles.sugEx} maxFontSizeMultiplier={1.3}>{s.exercise_name}</Text>
                <Badge label={labelFor(s.action)} tone={actionTone(s.action)} />
              </View>
              <Text style={styles.sugMsg} maxFontSizeMultiplier={1.6}>{s.message}</Text>
            </Card>
          ))}
          <View style={{ marginTop: 20 }}>
            <Button title="Done" onPress={onDone} variant="primary" />
          </View>
        </ScrollView>
      </View>
    );
  }

  // logging
  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: theme.colors.background }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        contentContainerStyle={styles.container}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="interactive"
      >
        <Text style={styles.title} maxFontSizeMultiplier={1.3}>{day.name}</Text>
        <View style={styles.progressRow}>
          <ProgressBar progress={totalSetsTarget > 0 ? totalSetsLogged / totalSetsTarget : 0} />
          <Text style={styles.progressText} maxFontSizeMultiplier={1.5}>
            {totalSetsLogged} of {totalSetsTarget} sets logged
          </Text>
        </View>
        <Text style={styles.rirHint} maxFontSizeMultiplier={1.6}>{RIR_HINT}</Text>
        {error ? <Text style={styles.error} maxFontSizeMultiplier={1.5}>{error}</Text> : null}

        {/* Always-visible "where am I" banner so the user never has to hunt for their place. */}
        {!allDone ? (
          <Card style={{ marginTop: 4 }} accentColor={theme.colors.accent}>
            <Text style={styles.nowLabel} maxFontSizeMultiplier={1.4}>NOW LOGGING</Text>
            <View style={styles.nowRow}>
              <Text style={styles.nowExercise} numberOfLines={1} maxFontSizeMultiplier={1.3}>
                {day.exercises[activeIndex].name}
              </Text>
              <Badge
                label={`Set ${Math.min((counts[day.exercises[activeIndex].name] ?? 0) + 1, day.exercises[activeIndex].sets)} of ${day.exercises[activeIndex].sets}`}
                tone="accent"
              />
            </View>
            <View style={{ marginTop: 8 }}>
              <SetDots
                total={day.exercises[activeIndex].sets}
                completed={counts[day.exercises[activeIndex].name] ?? 0}
                current={counts[day.exercises[activeIndex].name] ?? 0}
              />
            </View>
          </Card>
        ) : (
          <Card style={{ marginTop: 4 }} accentColor={theme.colors.success}>
            <Text style={[styles.nowLabel, { color: theme.colors.success }]}>ALL SETS LOGGED</Text>
            <Text style={styles.nowExercise} maxFontSizeMultiplier={1.3}>Nice work — ready to finish up?</Text>
          </Card>
        )}

        <RestTimerCard
          theme={theme}
          restLeft={restLeft}
          restTotal={restTotal}
          onExtend={() => setRestLeft((r) => (r ?? 0) + 30)}
          onSkip={() => setRestLeft(null)}
        />

        {day.exercises.map((ex, i) => (
          <ExerciseLogger
            key={`${ex.name}-${i}`}
            ex={ex}
            logged={counts[ex.name] ?? 0}
            last={lastPerf[ex.name]}
            loggedSets={(session?.sets ?? []).filter((s) => s.exercise_name === ex.name)}
            isActive={i === activeIndex}
            isDone={(counts[ex.name] ?? 0) >= ex.sets}
            onLog={(w, reps, rir) => logSet(ex, w, reps, rir)}
          />
        ))}

        <View style={{ marginTop: 16 }}>
          <Button
            title="Finish workout"
            onPress={finish}
            variant="success"
            loading={busy}
            disabled={busy}
          />
        </View>
        {!allDone ? (
          <Text style={styles.finishHint} maxFontSizeMultiplier={1.6}>
            {totalSetsTarget - totalSetsLogged} set{totalSetsTarget - totalSetsLogged === 1 ? "" : "s"} not yet logged — you can still finish early.
          </Text>
        ) : null}
        <Pressable onPress={confirmCancel} style={styles.cancelBtn} hitSlop={8}>
          <Text style={styles.cancelText} maxFontSizeMultiplier={1.4}>Cancel workout</Text>
        </Pressable>
        <View style={{ height: 220 }} />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

/** Countdown card between sets: pulses while active, with +30s and Skip. */
function RestTimerCard({
  theme,
  restLeft,
  restTotal,
  onExtend,
  onSkip,
}: {
  theme: Theme;
  restLeft: number | null;
  restTotal: number;
  onExtend: () => void;
  onSkip: () => void;
}) {
  const active = restLeft !== null;
  const pulse = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (!active) return;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1.03, duration: 700, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 1, duration: 700, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [active, pulse]);

  return (
    <Animated.View style={{ transform: [{ scale: active ? pulse : 1 }] }}>
      <Card
        padded
        style={[
          restStyles.card,
          { backgroundColor: active ? theme.colors.success : theme.colors.backgroundElevated2 },
        ]}
      >
        <Text style={[restStyles.label, { color: active ? "#FFFFFF" : theme.colors.textSecondary }]} maxFontSizeMultiplier={1.4}>
          {active ? "RESTING" : "REST TIMER"}
        </Text>
        <View style={restStyles.row}>
          <Text style={[restStyles.time, { color: active ? "#FFFFFF" : theme.colors.textSecondary }]} maxFontSizeMultiplier={1.2}>
            {active ? `${Math.floor((restLeft ?? 0) / 60)}:${String((restLeft ?? 0) % 60).padStart(2, "0")}` : "Log a set to start"}
          </Text>
          {active ? (
            <View style={restStyles.actions}>
              <Pressable style={restStyles.pill} onPress={onExtend} hitSlop={6}>
                <Text style={restStyles.pillText}>+30s</Text>
              </Pressable>
              <Pressable style={restStyles.pill} onPress={onSkip} hitSlop={6}>
                <Text style={restStyles.pillText}>Skip</Text>
              </Pressable>
            </View>
          ) : null}
        </View>
        {active ? (
          <View style={{ marginTop: 10 }}>
            <ProgressBar
              progress={1 - (restLeft ?? 0) / Math.max(1, restTotal)}
              color="rgba(255,255,255,0.9)"
              trackColor="rgba(255,255,255,0.25)"
            />
          </View>
        ) : null}
      </Card>
    </Animated.View>
  );
}

/** One exercise's logging card: dots, per-set history chips, last-time note,
 * and weight/reps/RIR steppers. Collapses once its target sets are done. */
function ExerciseLogger({
  ex,
  logged,
  last,
  loggedSets,
  isActive,
  isDone,
  onLog,
}: {
  ex: ProgramExercise;
  logged: number;
  last?: { weight: number | null; reps: number; rir: number };
  loggedSets: SetLog[];
  isActive: boolean;
  isDone: boolean;
  onLog: (weight: number | null, reps: number, rir: number) => void;
}) {
  const theme = useTheme();
  const styles = useMemo(() => getExStyles(theme), [theme]);
  const [weight, setWeight] = useState(last?.weight != null ? String(last.weight) : "");
  const [reps, setReps] = useState(last?.reps != null ? String(last.reps) : "");
  const [rir, setRir] = useState(last?.rir != null ? String(last.rir) : "2");
  const [expanded, setExpanded] = useState(true);

  const canLog = reps.trim() !== "";
  const nextSetNumber = Math.min(logged + 1, ex.sets);
  const showCollapsed = isDone && !expanded;

  return (
    <Card
      style={[styles.card, isActive && { borderColor: theme.colors.accent }]}
      accentColor={isActive ? theme.colors.accent : isDone ? theme.colors.success : undefined}
    >
      <View style={styles.headerRow}>
        <View style={{ flex: 1 }}>
          <Text style={styles.exName} maxFontSizeMultiplier={1.3}>{ex.name}</Text>
          <Text style={styles.exTarget} maxFontSizeMultiplier={1.6}>
            {ex.sets} × {ex.reps} · RIR {ex.rir} · rest {ex.rest_seconds}s
          </Text>
        </View>
        {isDone ? (
          <Badge label="Done" tone="success" />
        ) : (
          <Badge label={`Set ${nextSetNumber} of ${ex.sets}`} tone={isActive ? "accent" : "neutral"} />
        )}
      </View>

      <View style={{ marginTop: 10 }}>
        <SetDots total={ex.sets} completed={logged} current={logged} />
      </View>

      {loggedSets.length > 0 ? (
        <View style={styles.historyRow}>
          {loggedSets.map((s) => (
            <View key={s.id} style={styles.historyChip}>
              <Text style={styles.historyText} maxFontSizeMultiplier={1.4}>
                #{s.set_number} · {s.weight != null ? `${s.weight}lb×` : ""}{s.reps}
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      {last ? (
        <Text style={styles.lastNote} maxFontSizeMultiplier={1.6}>
          Last time: {last.weight != null ? `${last.weight} lb × ` : ""}{last.reps} reps @ RIR {last.rir}
        </Text>
      ) : null}

      {showCollapsed ? (
        <Pressable onPress={() => setExpanded(true)} style={{ marginTop: 10 }}>
          <Text style={styles.reopenLink}>+ Log another set</Text>
        </Pressable>
      ) : (
        <>
          <View style={styles.inputs}>
            <Stepper label="Weight" value={weight} onChange={setWeight} step={5} allowDecimal max={2000} suffix="lb" />
            <Stepper label="Reps" value={reps} onChange={setReps} step={1} max={100} />
            <Stepper label="RIR" value={rir} onChange={setRir} step={1} min={0} max={10} />
          </View>
          <View style={{ marginTop: 10 }}>
            <Button
              title={`Log set ${nextSetNumber} of ${ex.sets}`}
              onPress={() => {
                onLog(weight.trim() === "" ? null : Number(weight), parseInt(reps, 10) || 0, parseInt(rir, 10) || 0);
                if (isDone) setExpanded(false);
              }}
              variant={isDone ? "secondary" : "primary"}
              disabled={!canLog}
              size="medium"
            />
          </View>
        </>
      )}
    </Card>
  );
}

/** Display label / tone / accent color for a progression action string. */
function labelFor(a: string) {
  return a === "increase_load" ? "↑ Add load" : a === "reduce_load" ? "↓ Reduce load" : "→ Hold";
}
function actionTone(a: string): "success" | "danger" | "neutral" {
  return a === "increase_load" ? "success" : a === "reduce_load" ? "danger" : "neutral";
}
function actionColor(a: string, theme: Theme) {
  return a === "increase_load" ? theme.colors.success : a === "reduce_load" ? theme.colors.danger : theme.colors.border;
}

function getStyles(theme: Theme) {
  return StyleSheet.create({
    center: { flexGrow: 1, justifyContent: "center", padding: 24, gap: 8 },
    container: { padding: 20, gap: 14, paddingBottom: 8 },
    title: { fontSize: 26, fontWeight: "700", color: theme.colors.text },
    subtitle: { fontSize: 14, color: theme.colors.textSecondary, lineHeight: 19 },
    progressRow: { gap: 6 },
    progressText: { fontSize: 12, fontWeight: "600", color: theme.colors.textSecondary },
    readinessCard: { flexDirection: "row", alignItems: "center", gap: 14, paddingVertical: 14 },
    readinessIcon: { fontSize: 24 },
    readinessNum: { fontSize: 16, fontWeight: "600", color: theme.colors.text },
    chevron: { fontSize: 20 },
    error: { color: theme.colors.danger, fontWeight: "600" },
    link: { color: theme.colors.accent, fontWeight: "600", textAlign: "center" },
    finishHint: { fontSize: 12, color: theme.colors.textTertiary, textAlign: "center", marginTop: 8 },
    rirHint: { fontSize: 12, color: theme.colors.textTertiary },
    cancelBtn: { marginTop: 14, minHeight: 44, alignItems: "center", justifyContent: "center" },
    cancelText: { color: theme.colors.danger, fontWeight: "600", fontSize: 14 },
    nowLabel: { fontSize: 11, fontWeight: "700", letterSpacing: 0.6, color: theme.colors.accent, marginBottom: 4 },
    nowRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 },
    nowExercise: { fontSize: 18, fontWeight: "700", color: theme.colors.text, flex: 1 },
    doneBadgeWrap: { alignItems: "center", marginTop: 8, marginBottom: 4 },
    doneCheck: {
      fontSize: 34, fontWeight: "700", color: theme.colors.success,
      width: 64, height: 64, lineHeight: 64, textAlign: "center", borderRadius: 32,
      backgroundColor: theme.colors.successSoft, overflow: "hidden",
    },
    xpRow: { flexDirection: "row", alignItems: "center", gap: 10 },
    xpChip: {
      backgroundColor: theme.colors.accent,
      borderRadius: theme.radius.pill,
      paddingHorizontal: 12,
      paddingVertical: 5,
    },
    xpChipText: { fontSize: 14, fontWeight: "800", color: "#FFFFFF" },
    xpMeta: { fontSize: 13, fontWeight: "600", color: theme.colors.textSecondary, flex: 1 },
    unlockBanner: {
      backgroundColor: theme.colors.warningSoft,
      borderRadius: theme.radius.md,
      paddingVertical: 8,
      paddingHorizontal: 12,
    },
    unlockText: { fontSize: 13, fontWeight: "700", color: theme.colors.warning },
    sugHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 },
    sugEx: { fontSize: 16, fontWeight: "700", color: theme.colors.text, flex: 1 },
    sugMsg: { fontSize: 13, color: theme.colors.textSecondary, marginTop: 6, lineHeight: 18 },
  });
}

const restStyles = StyleSheet.create({
  card: { paddingVertical: 14 },
  label: { fontSize: 11, fontWeight: "700", letterSpacing: 0.6 },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 4 },
  time: { fontSize: 24, fontWeight: "700" },
  actions: { flexDirection: "row", gap: 8 },
  pill: { backgroundColor: "rgba(255,255,255,0.25)", borderRadius: 8, paddingVertical: 8, paddingHorizontal: 14 },
  pillText: { color: "#FFFFFF", fontWeight: "700", fontSize: 13 },
});

function getExStyles(theme: Theme) {
  return StyleSheet.create({
    card: { gap: 0 },
    headerRow: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 10 },
    exName: { fontSize: 16, fontWeight: "700", color: theme.colors.text },
    exTarget: { fontSize: 12, color: theme.colors.textSecondary, marginTop: 2 },
    historyRow: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 10 },
    historyChip: {
      backgroundColor: theme.colors.backgroundElevated2, borderRadius: theme.radius.pill,
      paddingVertical: 4, paddingHorizontal: 10,
    },
    historyText: { fontSize: 11, fontWeight: "600", color: theme.colors.textSecondary },
    lastNote: { fontSize: 12, color: theme.colors.accent, fontWeight: "600", marginTop: 8 },
    reopenLink: { fontSize: 13, fontWeight: "600", color: theme.colors.accent },
    inputs: { flexDirection: "row", alignItems: "flex-end", gap: 8, marginTop: 14 },
  });
}
