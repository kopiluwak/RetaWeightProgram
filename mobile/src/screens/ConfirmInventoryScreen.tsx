import React, { useMemo, useState } from "react";
import { Alert, Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { EquipmentItem, InventoryApi, InventoryVersion } from "../api";
import { EQUIPMENT_TYPES, prettyType } from "../equipment";
import { friendlyError } from "../errors";
import { Theme, useTheme } from "../theme";
import { Badge, Button, Card, ScreenBackground } from "../ui";

// Mandatory confirmation step (spec R1/R3): the recognized draft is editable;
// nothing is canonical until the user confirms.
export default function ConfirmInventoryScreen({
  draft,
  onConfirmed,
  onBack,
}: {
  draft: InventoryVersion;
  onConfirmed: (confirmed: InventoryVersion) => void;
  onBack?: () => void;
}) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const [items, setItems] = useState<EquipmentItem[]>(draft.items);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pickerIdx, setPickerIdx] = useState<number | null>(null);

  function update(idx: number, patch: Partial<EquipmentItem>) {
    setItems((prev) => prev.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  }
  function remove(idx: number) {
    setItems((prev) => prev.filter((_, i) => i !== idx));
  }
  function confirmRemove(idx: number) {
    Alert.alert(`Remove ${prettyType(items[idx].type)}?`, "You can add it back with “+ Add item”.", [
      { text: "Cancel", style: "cancel" },
      { text: "Remove", style: "destructive", onPress: () => remove(idx) },
    ]);
  }
  function add() {
    setItems((prev) => [
      ...prev,
      { type: "barbell", quantity: 1, load_min: null, load_max: null, load_increment: null, attributes: {} },
    ]);
  }
  function numField(idx: number, key: "load_min" | "load_max", v: string) {
    const n = v.trim() === "" ? null : Number(v.replace(/[^0-9.]/g, ""));
    update(idx, { [key]: Number.isNaN(n as number) ? null : n } as Partial<EquipmentItem>);
  }

  async function confirm() {
    setError(null);
    setSaving(true);
    try {
      const result = await InventoryApi.confirm(draft.id, items);
      onConfirmed(result);
    } catch (e) {
      setError(friendlyError(e, "Could not confirm"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <ScreenBackground onBack={onBack} backLabel="Retake">
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title} maxFontSizeMultiplier={1.3}>Confirm your equipment</Text>
        <Text style={styles.subtitle} maxFontSizeMultiplier={1.7}>
          We detected the items below. Fix anything wrong — especially weights, which
          cameras can't read reliably — then confirm.
        </Text>

        {items.map((it, idx) => (
          <Card key={it.id ?? `new-${idx}`} style={styles.card}>
            <Pressable
              onPress={() => setPickerIdx(idx)}
              accessibilityRole="button"
              accessibilityLabel={`Type: ${prettyType(it.type)}. Tap to change.`}
              style={styles.typeRow}
            >
              <Text style={styles.typeText} maxFontSizeMultiplier={1.3}>{prettyType(it.type)}</Text>
              <Text style={styles.typeChange}>Change ›</Text>
            </Pressable>

            {typeof it.confidence === "number" ? (
              <View style={{ alignItems: "center", marginTop: 6 }}>
                <Badge
                  label={`detected · ${Math.round(it.confidence * 100)}% confidence${it.confidence < 0.6 ? " — double-check" : ""}`}
                  tone={it.confidence < 0.6 ? "warning" : "neutral"}
                />
              </View>
            ) : null}

            <View style={styles.fieldRow}>
              <Field label="Qty" value={String(it.quantity)}
                onChange={(v) => update(idx, { quantity: Math.max(1, parseInt(v || "1", 10) || 1) })} theme={theme} />
              <Field label="Min lb" value={it.load_min?.toString() ?? ""}
                onChange={(v) => numField(idx, "load_min", v)} theme={theme} />
              <Field label="Max lb" value={it.load_max?.toString() ?? ""}
                onChange={(v) => numField(idx, "load_max", v)} theme={theme} />
            </View>

            <Pressable onPress={() => confirmRemove(idx)} style={styles.removeBtn} hitSlop={8}>
              <Text style={styles.removeText}>Remove</Text>
            </Pressable>
          </Card>
        ))}

        <Pressable style={styles.addBtn} onPress={add}>
          <Text style={styles.addText}>+ Add item</Text>
        </Pressable>

        {error ? <Text style={styles.error} maxFontSizeMultiplier={1.6}>{error}</Text> : null}

        <View style={{ marginTop: 4, marginBottom: 24 }}>
          <Button
            title="Confirm inventory"
            onPress={confirm}
            loading={saving}
            disabled={items.length === 0 || saving}
            variant="primary"
          />
        </View>
      </ScrollView>

      <Modal
        visible={pickerIdx !== null}
        transparent
        animationType="slide"
        onRequestClose={() => setPickerIdx(null)}
      >
        <Pressable style={styles.modalBackdrop} onPress={() => setPickerIdx(null)}>
          <Pressable style={styles.modalSheet} onPress={() => {}}>
            <Text style={styles.modalTitle} maxFontSizeMultiplier={1.3}>Choose equipment type</Text>
            <ScrollView style={{ maxHeight: 380 }}>
              {EQUIPMENT_TYPES.map((t) => {
                const selected = pickerIdx !== null && items[pickerIdx]?.type === t;
                return (
                  <Pressable
                    key={t}
                    onPress={() => {
                      if (pickerIdx !== null) update(pickerIdx, { type: t });
                      setPickerIdx(null);
                    }}
                    style={[styles.modalRow, selected && { backgroundColor: theme.colors.backgroundElevated2 }]}
                    accessibilityRole="button"
                    accessibilityState={{ selected }}
                  >
                    <Text style={[styles.modalRowText, selected && { color: theme.colors.accent, fontWeight: "700" }]} maxFontSizeMultiplier={1.4}>
                      {prettyType(t)}
                    </Text>
                    {selected ? <Text style={styles.modalCheck}>✓</Text> : null}
                  </Pressable>
                );
              })}
            </ScrollView>
            <Button title="Cancel" onPress={() => setPickerIdx(null)} variant="ghost" size="medium" />
          </Pressable>
        </Pressable>
      </Modal>
    </ScreenBackground>
  );
}

/** Small labeled numeric input used for quantity and load ranges. */
function Field({ label, value, onChange, theme }: { label: string; value: string; onChange: (v: string) => void; theme: Theme }) {
  return (
    <View style={{ flex: 1 }}>
      <Text style={{ fontSize: 12, color: theme.colors.textSecondary, marginBottom: 4, fontWeight: "600" }}>{label}</Text>
      <TextInput
        style={{
          borderWidth: 1, borderColor: theme.colors.border, borderRadius: theme.radius.sm, padding: 10,
          fontSize: 15, color: theme.colors.text, backgroundColor: theme.colors.backgroundElevated2,
        }}
        value={value}
        onChangeText={onChange}
        keyboardType="numeric"
      />
    </View>
  );
}

function getStyles(theme: Theme) {
  return StyleSheet.create({
    container: { padding: 20, gap: 12 },
    title: { fontSize: 24, fontWeight: "700", color: theme.colors.text, marginTop: 8 },
    subtitle: { fontSize: 13, color: theme.colors.textSecondary, marginBottom: 8, lineHeight: 18 },
    card: { gap: 8 },
    typeRow: {
      flexDirection: "row", alignItems: "center", justifyContent: "space-between",
      minHeight: 44, paddingVertical: 4,
    },
    typeText: { fontSize: 17, fontWeight: "700", color: theme.colors.text },
    typeChange: { fontSize: 14, fontWeight: "700", color: theme.colors.accent },
    fieldRow: { flexDirection: "row", gap: 10, marginTop: 8 },
    removeBtn: { marginTop: 8, minHeight: 44, justifyContent: "center" },
    removeText: { color: theme.colors.danger, fontSize: 13, fontWeight: "600" },
    modalBackdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end" },
    modalSheet: {
      backgroundColor: theme.colors.backgroundElevated,
      borderTopLeftRadius: theme.radius.xl, borderTopRightRadius: theme.radius.xl,
      padding: 20, gap: 6,
    },
    modalTitle: { fontSize: 18, fontWeight: "700", color: theme.colors.text, marginBottom: 8 },
    modalRow: {
      flexDirection: "row", alignItems: "center", justifyContent: "space-between",
      paddingVertical: 14, paddingHorizontal: 12, borderRadius: theme.radius.md, minHeight: 48,
    },
    modalRowText: { fontSize: 16, color: theme.colors.text },
    modalCheck: { fontSize: 16, fontWeight: "800", color: theme.colors.accent },
    addBtn: {
      borderWidth: 1, borderColor: theme.colors.text, borderStyle: "dashed",
      borderRadius: theme.radius.lg, padding: 14, alignItems: "center",
    },
    addText: { fontWeight: "700", color: theme.colors.text },
    error: { color: theme.colors.danger, fontWeight: "600" },
  });
}
