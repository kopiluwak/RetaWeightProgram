// Auth step 2: enter the emailed 6-digit code to complete sign-in.
import React, { useMemo, useRef, useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { AuthApi } from "../api";
import { friendlyError } from "../errors";
import { Theme, useTheme } from "../theme";
import { Button, ScreenBackground } from "../ui";

/** Code entry + resend; onVerified() fires after tokens are stored. */
export default function OtpEntryScreen({
  email,
  onVerified,
  onBack,
}: {
  email: string;
  onVerified: () => void;
  onBack: () => void;
}) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resendMsg, setResendMsg] = useState<string | null>(null);
  const [resendCooldown, setResendCooldown] = useState(0);
  const submittedFor = useRef<string | null>(null);

  const valid = /^\d{6}$/.test(code);

  async function submit(value: string = code) {
    if (!/^\d{6}$/.test(value) || loading) return;
    setError(null);
    setLoading(true);
    try {
      await AuthApi.verifyOtp(email, value);
      onVerified();
    } catch (e) {
      setError(friendlyError(e));
      submittedFor.current = null; // allow re-attempt on a corrected code
    } finally {
      setLoading(false);
    }
  }

  // Auto-submit once a full 6-digit code is present (e.g. from OTP autofill),
  // but only once per distinct code so a failed attempt doesn't loop.
  function onChangeCode(t: string) {
    const digits = t.replace(/\D/g, "").slice(0, 6);
    setCode(digits);
    if (digits.length === 6 && submittedFor.current !== digits) {
      submittedFor.current = digits;
      submit(digits);
    }
  }

  function startCooldown() {
    setResendCooldown(30);
    const id = setInterval(() => {
      setResendCooldown((s) => {
        if (s <= 1) {
          clearInterval(id);
          return 0;
        }
        return s - 1;
      });
    }, 1000);
  }

  async function resend() {
    if (resendCooldown > 0) return;
    setError(null);
    setResendMsg(null);
    try {
      await AuthApi.requestOtp(email);
      setResendMsg("New code sent.");
      startCooldown();
    } catch (e) {
      setError(friendlyError(e, "Could not resend"));
    }
  }

  return (
    <ScreenBackground>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <View style={styles.container}>
        <Text style={styles.title} maxFontSizeMultiplier={1.3}>Enter your code</Text>
        <Text style={styles.subtitle} maxFontSizeMultiplier={1.6}>Sent to {email}. Expires in 10 minutes.</Text>

        <TextInput
          style={styles.code}
          placeholder="000000"
          placeholderTextColor={theme.colors.textTertiary}
          keyboardType="number-pad"
          textContentType="oneTimeCode"
          autoComplete="one-time-code"
          autoFocus
          maxLength={6}
          value={code}
          onChangeText={onChangeCode}
        />

        {error ? <Text style={styles.error} maxFontSizeMultiplier={1.6}>{error}</Text> : null}
        {resendMsg && !error ? <Text style={styles.notice} maxFontSizeMultiplier={1.6}>{resendMsg}</Text> : null}

        <View style={{ marginTop: 8 }}>
          <Button title="Verify" onPress={() => submit()} loading={loading} disabled={!valid || loading} variant="primary" />
        </View>

        <View style={styles.row}>
          <Pressable onPress={onBack} hitSlop={10} style={styles.linkBtn}>
            <Text style={styles.link}>Change email</Text>
          </Pressable>
          <Pressable onPress={resend} disabled={resendCooldown > 0} hitSlop={10} style={styles.linkBtn}>
            <Text style={[styles.link, resendCooldown > 0 && styles.linkDisabled]}>
              {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : "Resend code"}
            </Text>
          </Pressable>
        </View>
      </View>
      </KeyboardAvoidingView>
    </ScreenBackground>
  );
}

function getStyles(theme: Theme) {
  return StyleSheet.create({
    container: { flex: 1, justifyContent: "center", padding: 24, gap: 12 },
    title: { fontSize: 28, fontWeight: "700", color: theme.colors.text },
    subtitle: { fontSize: 15, color: theme.colors.textSecondary, marginBottom: 12 },
    code: {
      borderWidth: 1, borderColor: theme.colors.border, borderRadius: 12, padding: 16,
      fontSize: 28, letterSpacing: 8, textAlign: "center", color: theme.colors.text,
      backgroundColor: theme.colors.backgroundElevated,
    },
    error: { color: theme.colors.danger, fontWeight: "600" },
    notice: { color: theme.colors.success, fontWeight: "600" },
    row: { flexDirection: "row", justifyContent: "space-between", marginTop: 14 },
    linkBtn: { minHeight: 44, justifyContent: "center" },
    link: { color: theme.colors.accent, fontWeight: "600" },
    linkDisabled: { color: theme.colors.textTertiary },
  });
}
