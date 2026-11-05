// Neutron: voice protein logging.
// Dictate a meal -> ON-DEVICE parse (bundled food DB + fuzzy matcher + alias
// cache + tiny Naive Bayes classifier) -> editable review cards -> log to
// /nutrition/log (source "voice"). AI (/nutrition/parse) is the LAST resort,
// only for phrases no local tier can resolve, and every answer is cached on
// device + server so the same phrase never hits the model twice.
// Speech recognition runs on-device where iOS supports it; offline logging
// goes to a local queue that flushes next time the screen opens.
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator, Keyboard, Pressable, ScrollView, StyleSheet, Text,
  TextInput, View,
} from "react-native";
import {
  ExpoSpeechRecognitionModule,
  useSpeechRecognitionEvent,
} from "expo-speech-recognition";
import { NutritionApi } from "../api";
import { Theme, useTheme } from "../theme";
import { Badge, Button, Card, ScreenBackground, Stepper } from "../ui";
import { normalize } from "../nutrition/matcher";
import { DraftItem, parseTranscript } from "../nutrition/parser";
import {
  cacheLookup, cachePut, enqueueLog, flushLogQueue, initVoiceStore,
  pendingLogCount,
} from "../nutrition/voiceStore";

/** Round to one decimal (protein grams display/logging precision). */
function round1(x: number): number { return Math.round(x * 10) / 10; }
/** Device timezone offset in minutes east of UTC (what the API expects). */
function tzMinutes(): number { return -new Date().getTimezoneOffset(); }

export default function VoiceLogScreen({ onBack }: { onBack: () => void }) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);

  const [recognizing, setRecognizing] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [typed, setTyped] = useState("");
  const [items, setItems] = useState<DraftItem[]>([]);
  const [editedIds, setEditedIds] = useState<Set<string>>(new Set());
  const [aiBusy, setAiBusy] = useState(false);
  const [logging, setLogging] = useState(false);
  const [result, setResult] = useState<{ total: number; target: number | null; message: string; badges: string[]; queued: number } | null>(null);
  const [pendingQueued, setPendingQueued] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const transcriptRef = useRef("");
  const onDeviceRef = useRef(false);

  // Boot the local store + drain any logs made offline last time.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        await initVoiceStore();
        await flushLogQueue(async (e) => {
          await NutritionApi.logProtein(e.grams, e.label, e.source, e.calories ?? undefined);
        });
        if (alive) setPendingQueued(await pendingLogCount());
      } catch { /* fully offline is fine — everything still works locally */ }
      try {
        onDeviceRef.current = ExpoSpeechRecognitionModule.supportsOnDeviceRecognition();
      } catch { onDeviceRef.current = false; }
    })();
    return () => { alive = false; };
  }, []);

  useSpeechRecognitionEvent("result", (event) => {
    const t = event.results?.[0]?.transcript ?? "";
    transcriptRef.current = t;
    setTranscript(t);
  });
  useSpeechRecognitionEvent("end", () => {
    setRecognizing(false);
    if (transcriptRef.current.trim()) runParse(transcriptRef.current);
  });
  useSpeechRecognitionEvent("error", (event) => {
    setRecognizing(false);
    if (event.error !== "no-speech") setError("Couldn't hear that — try again or type it below.");
  });

  async function toggleMic() {
    setError(null);
    setResult(null);
    if (recognizing) {
      try { ExpoSpeechRecognitionModule.stop(); } catch { setRecognizing(false); }
      return;
    }
    try {
      const perm = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
      if (!perm.granted) {
        setError("Microphone access is needed for voice logging — you can also type your meal below.");
        return;
      }
      transcriptRef.current = "";
      setTranscript("");
      setRecognizing(true);
      ExpoSpeechRecognitionModule.start({
        lang: "en-US",
        interimResults: true,
        continuous: false,
        // Privacy-first: keep recognition on the phone whenever iOS can.
        requiresOnDeviceRecognition: onDeviceRef.current,
        addsPunctuation: false,
      });
    } catch {
      setRecognizing(false);
      setError("Speech recognition isn't available on this device — type your meal below instead.");
    }
  }

  /** Local tiers, instantly; then (online only) refine the stragglers via AI. */
  function runParse(text: string) {
    const drafts = parseTranscript(text, cacheLookup);
    if (drafts.length === 0) {
      setError("Couldn't find any food in that — try e.g. “250 grams of chicken and a protein shake”.");
      return;
    }
    setItems((prev) => [...prev, ...drafts]);
    void refineWithAi(drafts);
  }

  async function refineWithAi(drafts: DraftItem[]) {
    const targets = drafts.filter((d) => d.needsAi);
    if (targets.length === 0) return;
    setAiBusy(true);
    try {
      const res = await NutritionApi.parseFoods(targets.map((t) => t.foodPhrase));
      for (const parsed of res.items) {
        if (parsed.protein_per_100g <= 0 && parsed.protein_g <= 0) continue;
        await cachePut(parsed.phrase, {
          name: parsed.name, proteinPer100g: parsed.protein_per_100g,
          portionEstG: parsed.portion_est_g, source: "ai",
        });
        const key = normalize(parsed.phrase);
        setItems((prev) => prev.map((d) => {
          if (normalize(d.foodPhrase) !== key || !d.needsAi || editedIds.has(d.id)) return d;
          // Classifier-tier portions were guesses — adopt the AI's portion.
          // Fuzzy-tier portions came from the user's own quantity — keep them.
          const portionG = d.tier === "classifier" ? round1(parsed.portion_est_g) : d.portionG;
          return {
            ...d, name: parsed.name, proteinPer100g: parsed.protein_per_100g,
            portionG, proteinG: round1((parsed.protein_per_100g * portionG) / 100),
            tier: "ai", confidence: parsed.confidence, needsAi: false,
          };
        }));
      }
    } catch { /* offline: local estimates stand, flagged as approximate */ }
    finally { setAiBusy(false); }
  }

  function markEdited(id: string) {
    setEditedIds((prev) => new Set(prev).add(id));
  }

  function updateItem(id: string, patch: Partial<DraftItem>) {
    setItems((prev) => prev.map((d) => (d.id === id ? { ...d, ...patch } : d)));
  }

  const totalG = round1(items.reduce((acc, d) => acc + (d.proteinG || 0), 0));

  async function logAll() {
    if (items.length === 0) return;
    Keyboard.dismiss();
    setLogging(true);
    setError(null);
    // Persist corrections FIRST so this session's fixes survive even if the
    // network log fails — next dictation of the same phrase parses right.
    for (const d of items) {
      if (editedIds.has(d.id) && d.portionG > 0 && d.proteinG >= 0) {
        await cachePut(d.foodPhrase, {
          name: d.name, proteinPer100g: round1((d.proteinG / d.portionG) * 100),
          portionEstG: d.portionG, source: "correction",
        });
      }
    }
    let last: { today_total_g: number; target_g: number | null; message: string; newly_earned_badges: string[] } | null = null;
    let queued = 0;
    const badges: string[] = [];
    for (const d of items) {
      const grams = round1(d.proteinG);
      if (grams <= 0) continue;
      try {
        const res = await NutritionApi.logProtein(grams, d.name.slice(0, 160), "voice");
        last = res;
        badges.push(...res.newly_earned_badges);
      } catch {
        await enqueueLog({ grams, calories: null, label: d.name.slice(0, 160), source: "voice", tzMinutes: tzMinutes() });
        queued += 1;
      }
    }
    setPendingQueued(await pendingLogCount());
    setResult({
      total: last ? round1(last.today_total_g) : totalG,
      target: last?.target_g ?? null,
      message: last?.message ?? (queued > 0 ? "Saved on your phone — will sync when you're back online." : ""),
      badges, queued,
    });
    setItems([]);
    setEditedIds(new Set());
    setTranscript("");
    transcriptRef.current = "";
    setLogging(false);
  }

  function submitTyped() {
    const text = typed.trim();
    if (!text) return;
    setError(null);
    setResult(null);
    setTyped("");
    Keyboard.dismiss();
    runParse(text);
  }

  return (
    <ScreenBackground onBack={onBack} backLabel="Nutrition">
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Text style={styles.title} maxFontSizeMultiplier={1.2}>Voice Log</Text>
        <Text style={styles.subtitle} maxFontSizeMultiplier={1.4}>
          Say what you ate — “250 grams of grilled chicken with some rice and a protein shake”.
        </Text>

        <Pressable onPress={toggleMic} accessibilityRole="button"
          accessibilityLabel={recognizing ? "Stop listening" : "Start voice logging"}>
          <View style={[styles.micButton, recognizing && { backgroundColor: theme.colors.danger }]}>
            <Text style={styles.micGlyph}>{recognizing ? "◼" : "🎙"}</Text>
            <Text style={styles.micLabel} maxFontSizeMultiplier={1.2}>
              {recognizing ? "Listening… tap to stop" : "Tap to speak"}
            </Text>
          </View>
        </Pressable>

        {recognizing || transcript ? (
          <Card style={{ gap: 4 }}>
            <Text style={styles.transcriptLabel} maxFontSizeMultiplier={1.4}>Heard</Text>
            <Text style={styles.transcript} maxFontSizeMultiplier={1.4}>
              {transcript || "…"}
            </Text>
          </Card>
        ) : null}

        <View style={styles.typedRow}>
          <TextInput
            style={styles.typedInput}
            placeholder="…or type your meal"
            placeholderTextColor={theme.colors.textTertiary}
            value={typed}
            onChangeText={setTyped}
            onSubmitEditing={submitTyped}
            returnKeyType="done"
            maxFontSizeMultiplier={1.4}
          />
          <Button title="Add" size="medium" fullWidth={false} variant="secondary" onPress={submitTyped} />
        </View>

        {error ? <Text style={styles.error} maxFontSizeMultiplier={1.4}>{error}</Text> : null}

        {result ? (
          <Card style={{ gap: 6 }}>
            <Text style={styles.resultTotal} maxFontSizeMultiplier={1.3}>
              {result.total} g today{result.target ? ` of ${Math.round(result.target)} g` : ""}
            </Text>
            {result.message ? <Text style={styles.hint} maxFontSizeMultiplier={1.5}>{result.message}</Text> : null}
            {result.badges.length > 0 ? (
              <View style={styles.badgeRow}>
                {result.badges.map((b) => <Badge key={b} label={`🏅 ${b}`} tone="success" />)}
              </View>
            ) : null}
            {result.queued > 0 ? (
              <Badge label={`${result.queued} saved offline — will sync`} tone="warning" />
            ) : null}
          </Card>
        ) : null}

        {items.map((d) => (
          <Card key={d.id} style={{ gap: 8 }}>
            <View style={styles.itemHeader}>
              <TextInput
                style={styles.itemName}
                value={d.name}
                onChangeText={(t) => { updateItem(d.id, { name: t }); markEdited(d.id); }}
                maxFontSizeMultiplier={1.3}
              />
              <Pressable onPress={() => setItems((prev) => prev.filter((x) => x.id !== d.id))}
                accessibilityRole="button" accessibilityLabel={`Remove ${d.name}`} hitSlop={10}>
                <Text style={styles.remove}>✕</Text>
              </Pressable>
            </View>
            <View style={styles.badgeRow}>
              <Badge label={d.portionLabel} tone="neutral" />
              {d.tier === "ai" ? <Badge label="AI estimate" tone="accent" />
                : d.needsAi || d.confidence < 0.6
                  ? <Badge label="approx — tap to fix" tone="warning" />
                  : d.tier === "cache" ? <Badge label="from your history" tone="success" /> : null}
              {aiBusy && d.needsAi ? <ActivityIndicator size="small" color={theme.colors.textTertiary} /> : null}
            </View>
            <Stepper
              label="Protein"
              value={String(d.proteinG)}
              onChange={(v: string) => {
                const n = parseFloat(v);
                updateItem(d.id, { proteinG: Number.isFinite(n) ? n : 0 });
                markEdited(d.id);
              }}
              step={1} min={0} max={400} suffix="g" allowDecimal
            />
          </Card>
        ))}

        {items.length > 0 ? (
          <Button
            title={`Log ${totalG} g protein (${items.length} item${items.length === 1 ? "" : "s"})`}
            variant="accent" onPress={logAll} loading={logging}
          />
        ) : null}

        {pendingQueued > 0 && !result ? (
          <Badge label={`${pendingQueued} offline log${pendingQueued === 1 ? "" : "s"} waiting to sync`} tone="warning" />
        ) : null}

        <Text style={styles.privacy} maxFontSizeMultiplier={1.6}>
          Your voice is transcribed on this phone when supported, and food matching runs
          on-device first. Only unrecognized food names are sent for an estimate — never audio.
        </Text>
      </ScrollView>
    </ScreenBackground>
  );
}

function getStyles(theme: Theme) {
  const { colors, spacing, typography, radius } = theme;
  return StyleSheet.create({
    container: { padding: spacing.lg, paddingBottom: spacing.xl * 2, gap: spacing.md },
    backText: { ...typography.subhead, color: colors.accent },
    title: { ...typography.title, color: colors.text },
    subtitle: { ...typography.subhead, color: colors.textSecondary },
    micButton: {
      backgroundColor: colors.accent, borderRadius: radius.lg,
      alignItems: "center", paddingVertical: spacing.lg, gap: 6,
    },
    micGlyph: { fontSize: 34 },
    micLabel: { ...typography.headline, color: "#fff" },
    transcriptLabel: { ...typography.caption, color: colors.textTertiary, textTransform: "uppercase" },
    transcript: { ...typography.body, color: colors.text },
    typedRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
    typedInput: {
      flex: 1, ...typography.body, color: colors.text,
      backgroundColor: colors.backgroundElevated, borderRadius: radius.md,
      paddingHorizontal: spacing.md, paddingVertical: 10,
      borderWidth: 1, borderColor: colors.border,
    },
    itemHeader: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
    itemName: {
      flex: 1, ...typography.headline, color: colors.text,
      borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border,
      paddingVertical: 2,
    },
    remove: { ...typography.headline, color: colors.textTertiary, paddingHorizontal: 4 },
    badgeRow: { flexDirection: "row", flexWrap: "wrap", gap: 6, alignItems: "center" },
    resultTotal: { ...typography.title2, color: colors.text },
    hint: { ...typography.footnote, color: colors.textSecondary },
    error: { ...typography.footnote, color: colors.danger },
    privacy: { ...typography.caption, color: colors.textTertiary, marginTop: spacing.sm },
  });
}
