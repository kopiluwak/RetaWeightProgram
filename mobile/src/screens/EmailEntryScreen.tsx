// Auth step 1: collect email (+ optional phone) and request an OTP code.
import React, { useMemo, useState } from "react";
import { KeyboardAvoidingView, Platform, StyleSheet, Text, TextInput, View } from "react-native";
import { AuthApi } from "../api";
import { friendlyError } from "../errors";
import { Theme, useTheme } from "../theme";
import { Button, ScreenBackground } from "../ui";

/** Email entry form; calls onCodeSent(email) once the code request succeeds. */
export default function EmailEntryScreen({ onCodeSent }: { onCodeSent: (email: string) => void }) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const valid = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim());

  async function submit() {
    setError(null);
    setLoading(true);
    try {
      await AuthApi.requestOtp(email.trim().toLowerCase(), phone.trim() || undefined);
      onCodeSent(email.trim().toLowerCase());
    } catch (e) {
      setError(friendlyError(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <ScreenBackground>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <View style={styles.container}>
        <Text style={styles.title} maxFontSizeMultiplier={1.3}>Sign in</Text>
        <Text style={styles.subtitle} maxFontSizeMultiplier={1.6}>We'll email you a 6-digit code. No password needed.</Text>

        <TextInput
          style={styles.input}
          placeholder="you@example.com"
          placeholderTextColor={theme.colors.textTertiary}
          autoCapitalize="none"
          keyboardType="email-address"
          autoComplete="email"
          textContentType="emailAddress"
          autoFocus
          returnKeyType="next"
          value={email}
          onChangeText={setEmail}
        />
        <TextInput
          style={styles.input}
          placeholder="Phone (optional)"
          placeholderTextColor={theme.colors.textTertiary}
          keyboardType="phone-pad"
          value={phone}
          onChangeText={setPhone}
        />

        {error ? <Text style={styles.error} maxFontSizeMultiplier={1.6}>{error}</Text> : null}

        <View style={{ marginTop: 8 }}>
          <Button title="Send code" onPress={submit} loading={loading} disabled={!valid || loading} variant="primary" />
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
    subtitle: { fontSize: 15, color: theme.colors.textSecondary, marginBottom: 12, lineHeight: 20 },
    input: {
      borderWidth: 1, borderColor: theme.colors.border, borderRadius: 12, padding: 14,
      fontSize: 16, color: theme.colors.text, backgroundColor: theme.colors.backgroundElevated,
    },
    error: { color: theme.colors.danger, fontWeight: "600" },
  });
}
