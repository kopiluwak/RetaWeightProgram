import React, { useEffect, useRef } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import * as Haptics from "expo-haptics";
import { useTheme } from "../theme";

/**
 * Fast numeric entry control used for weight / reps / RIR: large +/- targets
 * with press-and-hold acceleration, plus a directly-editable numeric field
 * for big jumps. Value is kept as a string so the field can be briefly empty
 * while the user is typing.
 */
export default function Stepper({
  label,
  value,
  onChange,
  step = 1,
  min = 0,
  max = 999,
  suffix,
  allowDecimal = false,
  accentColor,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  step?: number;
  min?: number;
  max?: number;
  suffix?: string;
  allowDecimal?: boolean;
  accentColor?: string;
}) {
  const theme = useTheme();
  const repeatInterval = useRef<ReturnType<typeof setInterval> | null>(null);
  const repeatDelay = useRef<ReturnType<typeof setTimeout> | null>(null);

  function clampRound(n: number) {
    const rounded = allowDecimal ? Math.round(n * 100) / 100 : Math.round(n);
    return Math.min(max, Math.max(min, rounded));
  }

  function bump(dir: 1 | -1) {
    const current = parseFloat(value || "0") || 0;
    const next = clampRound(current + dir * step);
    onChange(String(next));
    Haptics.selectionAsync().catch(() => {});
  }

  function stopRepeat() {
    if (repeatDelay.current) clearTimeout(repeatDelay.current);
    if (repeatInterval.current) clearInterval(repeatInterval.current);
    repeatDelay.current = null;
    repeatInterval.current = null;
  }

  function startRepeat(dir: 1 | -1) {
    bump(dir);
    repeatDelay.current = setTimeout(() => {
      repeatInterval.current = setInterval(() => bump(dir), 90);
    }, 420);
  }

  useEffect(() => stopRepeat, []);

  return (
    <View style={styles.wrap}>
      <Text style={[styles.label, { color: theme.colors.textSecondary }]} maxFontSizeMultiplier={1.3}>
        {label}
      </Text>
      <View style={[styles.row, { backgroundColor: theme.colors.backgroundElevated2, borderRadius: theme.radius.md }]}>
        <Pressable
          accessibilityLabel={`Decrease ${label}`}
          onPressIn={() => startRepeat(-1)}
          onPressOut={stopRepeat}
          hitSlop={8}
          style={({ pressed }) => [styles.btn, pressed && styles.btnPressed]}
        >
          <Text style={[styles.btnText, { color: theme.colors.text }]}>–</Text>
        </Pressable>

        <View style={styles.inputWrap}>
          <TextInput
            style={[styles.input, { color: theme.colors.text }]}
            value={value}
            onChangeText={(t) => onChange(t.replace(allowDecimal ? /[^0-9.]/g : /[^0-9]/g, ""))}
            keyboardType={allowDecimal ? "decimal-pad" : "number-pad"}
            selectTextOnFocus
            textAlign="center"
            maxFontSizeMultiplier={1.3}
          />
          {suffix ? (
            <Text style={[styles.suffix, { color: theme.colors.textTertiary }]} maxFontSizeMultiplier={1.2}>
              {suffix}
            </Text>
          ) : null}
        </View>

        <Pressable
          accessibilityLabel={`Increase ${label}`}
          onPressIn={() => startRepeat(1)}
          onPressOut={stopRepeat}
          hitSlop={8}
          style={({ pressed }) => [styles.btn, pressed && styles.btnPressed]}
        >
          <Text style={[styles.btnText, { color: accentColor ?? theme.colors.accent }]}>+</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, gap: 6 },
  label: { fontSize: 11, fontWeight: "700", letterSpacing: 0.4, textTransform: "uppercase" },
  row: { flexDirection: "row", alignItems: "center", height: 48 },
  btn: { width: 38, height: 48, alignItems: "center", justifyContent: "center" },
  btnPressed: { opacity: 0.45 },
  btnText: { fontSize: 22, fontWeight: "700" },
  inputWrap: { flex: 1, alignItems: "center", justifyContent: "center" },
  input: { fontSize: 20, fontWeight: "700", minWidth: 36, paddingVertical: 0 },
  suffix: { fontSize: 10, fontWeight: "700", marginTop: -2 },
});
