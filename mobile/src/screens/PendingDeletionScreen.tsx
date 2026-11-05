// Shown instead of the app whenever the signed-in account is inside its
// deletion grace window (App Store Review Guideline 5.1.1(v)).
//
// This is a hard gate on purpose. If the rest of the app stayed reachable, a
// user could keep logging workouts into an account that is scheduled to be
// destroyed — so the only two ways out are "keep my account" or signing out.
import React, { useMemo, useState } from "react";
import { ActivityIndicator, Alert, ScrollView, StyleSheet, Text, View } from "react-native";
import { AccountApi, Me } from "../api";
import { friendlyError } from "../errors";
import { Theme, useTheme } from "../theme";
import { Button, Card, ScreenBackground } from "../ui";

/** "17 September 2026" from an ISO string, falling back to the raw value. */
function prettyDate(iso?: string | null): string {
  if (!iso) return "soon";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
}

/** Whole days from now until the purge, floored at 0. */
function daysLeft(iso?: string | null): number | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  return Math.max(0, Math.ceil((d.getTime() - Date.now()) / 86_400_000));
}

export default function PendingDeletionScreen({
  me,
  onRestored,
  onSignOut,
}: {
  me: Me;
  onRestored: () => void;
  onSignOut: () => void;
}) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const [busy, setBusy] = useState(false);

  const when = prettyDate(me.deletion_scheduled_for);
  const left = daysLeft(me.deletion_scheduled_for);

  async function restore() {
    setBusy(true);
    try {
      await AccountApi.cancelDeletion();
      onRestored();
    } catch (e) {
      Alert.alert("Couldn't restore your account", friendlyError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <ScreenBackground showHome={false}>
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title} maxFontSizeMultiplier={1.2}>
          Your account is scheduled for deletion
        </Text>

        <Card style={{ gap: 10 }}>
          <Text style={styles.when} maxFontSizeMultiplier={1.2}>{when}</Text>
          <Text style={styles.body} maxFontSizeMultiplier={1.4}>
            {left === null
              ? "Your account and personal data will be permanently deleted."
              : left === 0
                ? "Your account and personal data will be permanently deleted today."
                : `That's ${left} day${left === 1 ? "" : "s"} from now. Until then, nothing has been deleted and you can restore everything.`}
          </Text>
        </Card>

        <Card style={{ gap: 8 }}>
          <Text style={styles.sectionTitle} maxFontSizeMultiplier={1.3}>What gets deleted</Text>
          <Text style={styles.body} maxFontSizeMultiplier={1.4}>
            Your email address, workout history, bodyweight and food logs, dietary
            preferences, generated programs, equipment inventory, and any equipment
            photos you chose to share.
          </Text>
          <Text style={styles.sectionTitle} maxFontSizeMultiplier={1.3}>What we keep</Text>
          <Text style={styles.body} maxFontSizeMultiplier={1.4}>
            Anonymous, aggregated training statistics only — counts of how much
            weight and how many reps people work at. These carry no link to you or
            to any individual.
          </Text>
        </Card>

        {busy ? (
          <ActivityIndicator size="large" color={theme.colors.text} style={{ marginTop: 12 }} />
        ) : (
          <View style={{ gap: 10 }}>
            <Button title="Keep my account" onPress={restore} />
            <Button title="Sign out" variant="secondary" onPress={onSignOut} />
          </View>
        )}

        <Text style={styles.footnote} maxFontSizeMultiplier={1.6}>
          Need help? Email support@glpsteel.com
        </Text>
      </ScrollView>
    </ScreenBackground>
  );
}

function getStyles(theme: Theme) {
  return StyleSheet.create({
    container: { padding: 20, gap: 14, paddingBottom: 40 },
    title: { ...theme.typography.title, color: theme.colors.text },
    when: { ...theme.typography.title2, color: theme.colors.danger },
    sectionTitle: { ...theme.typography.headline, color: theme.colors.text, marginTop: 4 },
    body: { ...theme.typography.subhead, color: theme.colors.textSecondary, lineHeight: 20 },
    footnote: { ...theme.typography.footnote, color: theme.colors.textTertiary, textAlign: "center" },
  });
}
