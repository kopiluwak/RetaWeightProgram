import React, { useCallback, useRef, useState } from "react";
import { Share, StyleSheet, Text, View } from "react-native";
import { captureRef } from "react-native-view-shot";

export type PrShareData = {
  exercise: string;
  value: number;    // new est. 1RM
  previous: number; // old best
  date: string;     // ISO date
};

/**
 * Shareable PR image (spec Su1): an off-screen branded card captured with
 * react-native-view-shot and handed to the native share sheet as a PNG.
 *
 * Usage:
 *   const { sharePr, shareNode } = usePrShare();
 *   ... {shareNode} ... onPress={() => sharePr(pr)}
 *
 * The card always uses the dark "gunmetal" palette regardless of system
 * appearance — it's leaving the app, so it should look like the brand.
 */
export function usePrShare() {
  const ref = useRef<View>(null);
  const [pr, setPr] = useState<PrShareData | null>(null);
  const busy = useRef(false);

  const sharePr = useCallback(async (data: PrShareData) => {
    if (busy.current) return;
    busy.current = true;
    try {
      setPr(data);
      // Give React a frame to mount the off-screen card before capturing.
      await new Promise((r) => setTimeout(r, 80));
      const uri = await captureRef(ref, { format: "png", quality: 1, result: "tmpfile" });
      const pct = data.previous > 0 ? Math.round((data.value / data.previous - 1) * 1000) / 10 : 0;
      await Share.share(
        {
          url: uri, // iOS: shares the PNG
          message: `New PR — ${data.exercise}: est. 1RM ${data.value} (+${pct}%)`,
        },
        { dialogTitle: "Share your PR" },
      );
    } catch {
      // User cancelled or capture failed — nothing to clean up.
    } finally {
      setPr(null);
      busy.current = false;
    }
  }, []);

  const pct = pr && pr.previous > 0 ? Math.round((pr.value / pr.previous - 1) * 1000) / 10 : 0;

  const shareNode = pr ? (
    <View style={styles.offscreen} collapsable={false} ref={ref}>
      <View style={styles.card}>
        <Text style={styles.brand}>WEIGHTPROGRAM</Text>
        <Text style={styles.banner}>NEW PR</Text>
        <Text style={styles.exercise} numberOfLines={2}>
          {pr.exercise}
        </Text>
        <View style={styles.valueRow}>
          <Text style={styles.value}>{pr.value}</Text>
          <Text style={styles.unit}> est. 1RM</Text>
        </View>
        <Text style={styles.delta}>
          {pr.previous} → {pr.value}  (+{pct}%)
        </Text>
        <Text style={styles.date}>
          {new Date(pr.date + "T12:00:00").toLocaleDateString(undefined, {
            month: "long",
            day: "numeric",
            year: "numeric",
          })}
        </Text>
        <View style={styles.barRow}>
          <View style={[styles.bar, { height: 18, opacity: 0.4 }]} />
          <View style={[styles.bar, { height: 28, opacity: 0.7 }]} />
          <View style={[styles.bar, { height: 40, opacity: 1 }]} />
        </View>
      </View>
    </View>
  ) : null;

  return { sharePr, shareNode };
}

// Brand palette, intentionally fixed (dark gunmetal + ember accent).
const styles = StyleSheet.create({
  offscreen: { position: "absolute", left: -9999, top: 0 },
  card: {
    width: 360,
    height: 360,
    backgroundColor: "#111315",
    borderRadius: 24,
    padding: 28,
    justifyContent: "flex-start",
  },
  brand: { color: "#767C82", fontSize: 12, fontWeight: "800", letterSpacing: 2 },
  banner: { color: "#FF8A50", fontSize: 15, fontWeight: "800", letterSpacing: 1.5, marginTop: 22 },
  exercise: { color: "#F5F6F7", fontSize: 28, fontWeight: "800", marginTop: 6, letterSpacing: -0.5 },
  valueRow: { flexDirection: "row", alignItems: "baseline", marginTop: 18 },
  value: { color: "#F5F6F7", fontSize: 56, fontWeight: "800", letterSpacing: -1 },
  unit: { color: "#A7ACB1", fontSize: 16, fontWeight: "600" },
  delta: { color: "#3DDC63", fontSize: 17, fontWeight: "700", marginTop: 6 },
  date: { color: "#767C82", fontSize: 13, fontWeight: "500", marginTop: 4 },
  barRow: {
    position: "absolute",
    right: 28,
    bottom: 28,
    flexDirection: "row",
    alignItems: "flex-end",
    gap: 6,
  },
  bar: { width: 12, borderRadius: 4, backgroundColor: "#FF8A50" },
});
