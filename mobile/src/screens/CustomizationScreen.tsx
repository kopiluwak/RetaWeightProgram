// Program customization: choose which equipment types to build with, or switch
// to bodyweight-only. Saving regenerates the program with the chosen filter and
// persists it (server-side) so future regenerations reuse the same preference.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { InventoryApi, ProgramApi } from "../api";
import { isStrengthType, prettyType } from "../equipment";
import { Theme, useTheme } from "../theme";
import { Button, Card, ScreenBackground } from "../ui";

export default function CustomizationScreen({
  onDone,
  onBack,
}: {
  onDone: () => void;   // program regenerated -> return to program view
  onBack: () => void;
}) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const [types, setTypes] = useState<string[]>([]);         // distinct strength types owned
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bodyweightOnly, setBodyweightOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const inv = await InventoryApi.current();
      const distinct = Array.from(
        new Set((inv?.items ?? []).map((it) => it.type).filter(isStrengthType))
      );
      setTypes(distinct);
      setSelected(new Set(distinct)); // default: everything on
    } catch {
      setTypes([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function toggle(t: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(t) ? next.delete(t) : next.add(t);
      return next;
    });
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      if (bodyweightOnly) {
        await ProgramApi.generate({ bodyweightOnly: true });
      } else {
        const chosen = types.filter((t) => selected.has(t));
        // Empty selection === "all" on the backend; guard so the user isn't
        // surprised by a silent full-equipment build.
        if (chosen.length === 0) {
          setError("Pick at least one equipment type, or switch on Bodyweight only.");
          setBusy(false);
          return;
        }
        await ProgramApi.generate({ bodyweightOnly: false, equipmentTypes: chosen });
      }
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not regenerate");
    } finally {
      setBusy(false);
    }
  }

  return (
    <ScreenBackground onBack={onBack} backLabel="Program">
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title} maxFontSizeMultiplier={1.3}>Customize your program</Text>
        <Text style={styles.subtitle} maxFontSizeMultiplier={1.6}>
          Pick the equipment to build with. Turn on Bodyweight only for a no-equipment plan.
        </Text>

        <Card style={styles.bwCard}>
          <View style={styles.rowBetween}>
            <View style={{ flex: 1, paddingRight: 12 }}>
              <Text style={styles.bwTitle} maxFontSizeMultiplier={1.3}>Bodyweight only</Text>
              <Text style={styles.bwCaption} maxFontSizeMultiplier={1.6}>
                Ignore all equipment and program movements you can do with just your body.
              </Text>
            </View>
            <Switch value={bodyweightOnly} onValueChange={setBodyweightOnly} />
          </View>
        </Card>

        {loading ? (
          <ActivityIndicator color={theme.colors.text} style={{ marginTop: 20 }} />
        ) : bodyweightOnly ? (
          <Text style={styles.dimNote} maxFontSizeMultiplier={1.6}>
            Equipment selection is off while Bodyweight only is on.
          </Text>
        ) : types.length === 0 ? (
          <Text style={styles.dimNote} maxFontSizeMultiplier={1.6}>
            No strength equipment in your inventory yet. Scan some, or use Bodyweight only.
          </Text>
        ) : (
          <View style={{ gap: 8, marginTop: 8 }}>
            <Text style={styles.sectionLabel}>Equipment to use</Text>
            {types.map((t) => (
              <View key={t} style={styles.typeRow}>
                <Text style={styles.typeText} maxFontSizeMultiplier={1.4}>{prettyType(t)}</Text>
                <Switch value={selected.has(t)} onValueChange={() => toggle(t)} />
              </View>
            ))}
          </View>
        )}

        {error ? <Text style={styles.error} maxFontSizeMultiplier={1.6}>{error}</Text> : null}

        <View style={{ marginTop: 20 }}>
          <Button title="Save & regenerate" onPress={save} loading={busy} disabled={busy} variant="primary" />
        </View>
      </ScrollView>
    </ScreenBackground>
  );
}

function getStyles(theme: Theme) {
  return StyleSheet.create({
    container: { padding: 20, gap: 12, paddingBottom: 40 },
    title: { fontSize: 24, fontWeight: "700", color: theme.colors.text, marginTop: 8 },
    subtitle: { fontSize: 13, color: theme.colors.textSecondary, lineHeight: 18 },
    bwCard: { marginTop: 8 },
    rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
    bwTitle: { fontSize: 16, fontWeight: "700", color: theme.colors.text },
    bwCaption: { fontSize: 12, color: theme.colors.textSecondary, marginTop: 3, lineHeight: 17 },
    sectionLabel: { fontSize: 13, fontWeight: "700", color: theme.colors.textSecondary, marginTop: 6 },
    typeRow: {
      flexDirection: "row", alignItems: "center", justifyContent: "space-between",
      paddingVertical: 10, paddingHorizontal: 14, borderRadius: theme.radius.md,
      backgroundColor: theme.colors.backgroundElevated,
      borderWidth: StyleSheet.hairlineWidth, borderColor: theme.colors.border,
    },
    typeText: { fontSize: 15, fontWeight: "600", color: theme.colors.text },
    dimNote: { fontSize: 13, color: theme.colors.textTertiary, marginTop: 16, lineHeight: 18 },
    error: { color: theme.colors.danger, fontWeight: "600", marginTop: 10 },
  });
}
