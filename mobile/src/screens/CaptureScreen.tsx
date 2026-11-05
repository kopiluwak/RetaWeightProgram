// Equipment capture: take/pick up to 4 photos, opt in (or not) to photo
// storage, and submit for recognition. The recognized DRAFT then goes to
// ConfirmInventoryScreen — nothing becomes canonical here.
import React, { useMemo, useState } from "react";
import { Image, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import * as ImagePicker from "expo-image-picker";
import { InventoryApi, InventoryVersion, PhotoAsset } from "../api";
import * as ImageManipulator from "expo-image-manipulator";
import { Theme, useTheme } from "../theme";
import { Button, ScreenBackground } from "../ui";

/** Photo capture + consent form; onRecognized(draft) advances to confirm.
 *  mode "add" merges into current inventory; "replace" is a full rescan. */
export default function CaptureScreen({
  onRecognized,
  onCancel,
  mode = "replace",
}: {
  onRecognized: (draft: InventoryVersion) => void;
  onCancel: () => void;
  mode?: "replace" | "add";
}) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const [photos, setPhotos] = useState<PhotoAsset[]>([]);
  const [consent, setConsent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function takePhoto() {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) {
      setError("Camera permission is required to photograph your equipment.");
      return;
    }
    const res = await ImagePicker.launchCameraAsync({ quality: 0.7 });
    addResult(res);
  }

  async function pickPhotos() {
    const res = await ImagePicker.launchImageLibraryAsync({
      quality: 0.7,
      allowsMultipleSelection: true,
    });
    addResult(res);
  }

  function addResult(res: ImagePicker.ImagePickerResult) {
    if (res.canceled) return;
    setPhotos((prev) =>
      [...prev, ...res.assets.map((a) => ({ uri: a.uri, mimeType: a.mimeType }))].slice(0, 4)
    );
  }

  async function submit() {
    setError(null);
    setLoading(true);
    try {
      // iOS photos are often HEIC, which the recognizer can't read — re-encode to JPEG.
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
      const draft = await InventoryApi.capture(jpegs, consent, mode);
      onRecognized(draft);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Recognition failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <ScreenBackground onBack={loading ? undefined : onCancel}>
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title} maxFontSizeMultiplier={1.3}>
          {mode === "add" ? "Add equipment" : "Scan your equipment"}
        </Text>
        <Text style={styles.subtitle} maxFontSizeMultiplier={1.7}>
          {mode === "add"
            ? "Photograph the new gear — we'll merge it into your current inventory. You'll confirm the combined list on the next screen."
            : "Photograph your weights, rack, bench, machines — pan around for multiple shots. You'll confirm what we detect on the next screen."}
        </Text>

        <View style={styles.row}>
          <View style={{ flex: 1 }}>
            <Button title="Take photo" onPress={takePhoto} variant="secondary" size="medium" />
          </View>
          <View style={{ flex: 1 }}>
            <Button title="Choose photos" onPress={pickPhotos} variant="secondary" size="medium" />
          </View>
        </View>

        {photos.length > 0 ? (
          <View style={styles.thumbs}>
            {photos.map((p, i) => (
              <Image key={`${p.uri}-${i}`} source={{ uri: p.uri }} style={styles.thumb} />
            ))}
          </View>
        ) : null}

        <View style={styles.consentRow}>
          <Switch value={consent} onValueChange={setConsent} />
          <Text style={styles.consentText} maxFontSizeMultiplier={1.7}>
            Store my photos to help improve recognition. We never share or sell them.
            Recognition works either way.
          </Text>
        </View>

        {error ? <Text style={styles.error} maxFontSizeMultiplier={1.6}>{error}</Text> : null}

        <View style={{ marginTop: 4 }}>
          <Button
            title="Detect equipment"
            onPress={submit}
            loading={loading}
            disabled={photos.length === 0 || loading}
            variant="primary"
          />
        </View>
      </ScrollView>
    </ScreenBackground>
  );
}

function getStyles(theme: Theme) {
  return StyleSheet.create({
    container: { padding: 24, gap: 14, flexGrow: 1, justifyContent: "center" },
    title: { fontSize: 26, fontWeight: "700", color: theme.colors.text },
    subtitle: { fontSize: 14, color: theme.colors.textSecondary, lineHeight: 19 },
    row: { flexDirection: "row", gap: 12 },
    thumbs: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
    thumb: { width: 72, height: 72, borderRadius: 10, backgroundColor: theme.colors.backgroundElevated2 },
    consentRow: { flexDirection: "row", alignItems: "center", gap: 10, marginTop: 8 },
    consentText: { flex: 1, fontSize: 13, color: theme.colors.textSecondary, lineHeight: 18 },
    error: { color: theme.colors.danger, fontWeight: "600" },
  });
}
