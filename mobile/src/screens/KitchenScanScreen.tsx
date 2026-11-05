// Neutron: "Scan My Kitchen" — photograph pantry/fridge/freezer shelves (or
// pick photos), send to the vision model, then review/edit the detected food
// list before saving it as the pantry. Photos are re-encoded to JPEG (iOS
// HEIC) and are never stored server-side; only the confirmed list persists.
import React, { useMemo, useState } from "react";
import { Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import * as ImagePicker from "expo-image-picker";
import * as ImageManipulator from "expo-image-manipulator";
import { NutritionApi, PhotoAsset, ScannedFoodItem } from "../api";
import { Theme, useTheme } from "../theme";
import { Badge, Button, Card, Chip, ScreenBackground } from "../ui";

type Phase = "capture" | "review";

type EditableItem = {
  name: string;
  quantity: string;
  category: string;
  protein_per_100g: number | null;
  protein_density: string;
  source: string;
  confidence: number | null;
};

const CATEGORIES = ["pantry", "fridge", "freezer", "other"];

export default function KitchenScanScreen({
  onSaved,
  onCancel,
}: {
  /** Called after the pantry list is saved; `generateNow` = user tapped the recipe CTA. */
  onSaved: (generateNow: boolean) => void;
  onCancel: () => void;
}) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const [phase, setPhase] = useState<Phase>("capture");
  const [photos, setPhotos] = useState<PhotoAsset[]>([]);
  const [items, setItems] = useState<EditableItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");

  async function takePhoto() {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) {
      setError("Camera permission is needed to photograph your kitchen.");
      return;
    }
    addResult(await ImagePicker.launchCameraAsync({ quality: 0.7 }));
  }

  async function pickPhotos() {
    addResult(await ImagePicker.launchImageLibraryAsync({ quality: 0.7, allowsMultipleSelection: true }));
  }

  function addResult(res: ImagePicker.ImagePickerResult) {
    if (res.canceled) return;
    setPhotos((prev) =>
      [...prev, ...res.assets.map((a) => ({ uri: a.uri, mimeType: a.mimeType }))].slice(0, 4)
    );
  }

  async function scan() {
    setError(null);
    setLoading(true);
    try {
      // iOS photos are often HEIC — re-encode to JPEG for the vision model.
      const jpegs = await Promise.all(
        photos.map(async (p) => {
          const r = await ImageManipulator.manipulateAsync(
            p.uri,
            [{ resize: { width: 1600 } }],
            { compress: 0.8, format: ImageManipulator.SaveFormat.JPEG }
          );
          return { uri: r.uri, mimeType: "image/jpeg" };
        })
      );
      const res = await NutritionApi.scanPantry(jpegs);
      if (res.items.length === 0) {
        // Never strand the user on an empty review screen — stay here and explain.
        setError(
          "We couldn't identify any food in those photos. Try getting closer, adding light, or scanning one shelf at a time — then scan again."
        );
        return;
      }
      setItems(res.items.map((s: ScannedFoodItem) => ({
        name: s.name, quantity: s.quantity, category: s.category,
        protein_per_100g: s.protein_per_100g, protein_density: s.protein_density,
        source: "scan", confidence: s.confidence,
      })));
      setPhase("review");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function updateItem(idx: number, patch: Partial<EditableItem>) {
    setItems((prev) => prev.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  }

  function removeItem(idx: number) {
    setItems((prev) => prev.filter((_, i) => i !== idx));
  }

  function addManual() {
    const name = newName.trim();
    if (!name) return;
    setItems((prev) => [...prev, {
      name, quantity: "", category: "pantry", protein_per_100g: null,
      protein_density: "low", source: "manual", confidence: null,
    }]);
    setNewName("");
  }

  async function save(generateNow: boolean) {
    setError(null);
    setSaving(true);
    try {
      await NutritionApi.replacePantry(items.filter((i) => i.name.trim().length > 0));
      onSaved(generateNow);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (phase === "review") {
    const highCount = items.filter((i) => i.protein_density === "high").length;
    return (
      <ScreenBackground>
        <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
          <Text style={styles.title} maxFontSizeMultiplier={1.2}>We found {items.length} items</Text>
          <Text style={styles.subtitle} maxFontSizeMultiplier={1.4}>
            Fix anything we got wrong, remove what you don't want, add what we missed.
            {highCount > 0 ? ` ${highCount} high-protein item${highCount === 1 ? "" : "s"} spotted — nice.` : ""}
          </Text>

          {items.map((it, idx) => (
            <Card key={idx} style={{ gap: 8 }}>
              <View style={styles.itemHeader}>
                <TextInput
                  style={[styles.input, { flex: 1 }]}
                  value={it.name}
                  onChangeText={(t) => updateItem(idx, { name: t })}
                  maxFontSizeMultiplier={1.4}
                />
                <Pressable onPress={() => removeItem(idx)} accessibilityRole="button" hitSlop={8}>
                  <Text style={styles.remove} maxFontSizeMultiplier={1.4}>Remove</Text>
                </Pressable>
              </View>
              <View style={styles.itemMetaRow}>
                <TextInput
                  style={[styles.input, { width: 110 }]}
                  value={it.quantity}
                  placeholder="quantity"
                  placeholderTextColor={theme.colors.textTertiary}
                  onChangeText={(t) => updateItem(idx, { quantity: t })}
                  maxFontSizeMultiplier={1.4}
                />
                {it.protein_density === "high" ? <Badge label="HIGH PROTEIN" tone="success" /> : null}
                {it.confidence != null && it.confidence < 0.6 ? <Badge label="LOW CONFIDENCE" tone="warning" /> : null}
              </View>
              <View style={styles.chipRow}>
                {CATEGORIES.map((c) => (
                  <Chip key={c} label={c} selected={it.category === c} onPress={() => updateItem(idx, { category: c })} />
                ))}
              </View>
            </Card>
          ))}

          <Card style={{ gap: 8 }}>
            <Text style={styles.sectionTitle} maxFontSizeMultiplier={1.3}>Add an item</Text>
            <View style={styles.itemHeader}>
              <TextInput
                style={[styles.input, { flex: 1 }]}
                value={newName}
                placeholder="e.g. cottage cheese"
                placeholderTextColor={theme.colors.textTertiary}
                onChangeText={setNewName}
                onSubmitEditing={addManual}
                returnKeyType="done"
                maxFontSizeMultiplier={1.4}
              />
              <Button title="Add" size="small" fullWidth={false} variant="secondary" onPress={addManual} />
            </View>
          </Card>

          {error ? <Text style={styles.error} maxFontSizeMultiplier={1.4}>{error}</Text> : null}
          <Button title="Save & Generate High-Protein Recipes" variant="accent"
            onPress={() => save(true)} loading={saving} disabled={items.length === 0} />
          <Button title="Just save my pantry" variant="secondary" onPress={() => save(false)} loading={saving} />
          <Button title="Back to photos" variant="ghost" onPress={() => setPhase("capture")} />
        </ScrollView>
      </ScreenBackground>
    );
  }

  return (
    <ScreenBackground>
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title} maxFontSizeMultiplier={1.2}>Scan My Kitchen</Text>
        <Text style={styles.subtitle} maxFontSizeMultiplier={1.4}>
          Take up to 4 photos of your pantry shelves, fridge, or freezer. We'll identify what you
          have and build high-protein recipes around it.
        </Text>

        <View style={styles.photoGrid}>
          {photos.map((p, i) => (
            <View key={i} style={styles.thumbWrap}>
              <Image source={{ uri: p.uri }} style={styles.thumb} />
              <Pressable style={styles.thumbRemove} hitSlop={8}
                onPress={() => setPhotos((prev) => prev.filter((_, idx) => idx !== i))}>
                <Text style={{ color: "#FFF", fontWeight: "800", fontSize: 12 }}>✕</Text>
              </Pressable>
            </View>
          ))}
        </View>

        <Button title="Take photo" onPress={takePhoto} variant="accent" />
        <Button title="Choose from library" onPress={pickPhotos} variant="secondary" />
        {error ? <Text style={styles.error} maxFontSizeMultiplier={1.4}>{error}</Text> : null}
        <Button title={`Scan ${photos.length} photo${photos.length === 1 ? "" : "s"}`}
          onPress={scan} loading={loading} disabled={photos.length === 0} />
        <Button title="Cancel" variant="ghost" onPress={onCancel} />

        <Text style={styles.privacy} maxFontSizeMultiplier={1.6}>
          Privacy: photos are sent over an encrypted connection for recognition only and are never
          stored. Only the food list you confirm on the next screen is saved to your account.
        </Text>
      </ScrollView>
    </ScreenBackground>
  );
}

function getStyles(theme: Theme) {
  return StyleSheet.create({
    container: { padding: 20, gap: 14, paddingBottom: 40 },
    title: { ...theme.typography.title, color: theme.colors.text, marginTop: 8 },
    subtitle: { ...theme.typography.subhead, color: theme.colors.textSecondary, lineHeight: 20 },
    sectionTitle: { ...theme.typography.headline, color: theme.colors.text },
    photoGrid: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
    thumbWrap: { position: "relative" },
    thumb: { width: 76, height: 76, borderRadius: theme.radius.md },
    thumbRemove: {
      position: "absolute", top: -6, right: -6, width: 22, height: 22, borderRadius: 11,
      backgroundColor: theme.colors.danger, alignItems: "center", justifyContent: "center",
    },
    itemHeader: { flexDirection: "row", alignItems: "center", gap: 10 },
    itemMetaRow: { flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap" },
    chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
    input: {
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.colors.border,
      borderRadius: theme.radius.md,
      paddingHorizontal: 10,
      paddingVertical: 8,
      color: theme.colors.text,
      backgroundColor: theme.colors.backgroundElevated2,
      ...theme.typography.body,
    },
    remove: { ...theme.typography.subhead, color: theme.colors.danger },
    error: { ...theme.typography.subhead, color: theme.colors.danger },
    privacy: { ...theme.typography.footnote, color: theme.colors.textTertiary, textAlign: "center", marginTop: 8 },
  });
}
