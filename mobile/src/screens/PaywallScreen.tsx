// Paywall. Shown at the FIRST SCAN gate (see PAYWALL_GATE in BillingContext)
// and reactively whenever the server answers 402.
//
// FOUR THINGS ON THIS SCREEN ARE APP REVIEW REQUIREMENTS, not design choices —
// a paywall missing any of them is rejected under Guideline 3.1.2 / 2.1:
//   1. the product's title and PRICE, shown before the purchase sheet opens;
//   2. for the subscription: its LENGTH and RENEWAL TERMS in plain language;
//   3. a RESTORE PURCHASES control;
//   4. links to the TERMS OF USE (EULA) and PRIVACY POLICY.
// If you edit this screen, keep all four. They are marked below.
import React, { useMemo, useState } from "react";
import { ActivityIndicator, Alert, Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useBilling } from "../BillingContext";
import { friendlyError } from "../errors";
import { Theme, useTheme } from "../theme";
import { Badge, Button, Card, ScreenBackground } from "../ui";

/** Apple's standard EULA — the Terms of Use link App Review looks for. Replace
 *  with your own hosted terms if you ever write custom ones. */
const TERMS_URL = "https://www.apple.com/legal/internet-services/itunes/dev/stdeula/";
const PRIVACY_URL = "https://api.glpsteel.com/privacy";

/** Copy per product. `price` here is only a FALLBACK for when the store price
 *  hasn't loaded (no SDK key yet, or offline) — the real, localized App Store
 *  price always wins, because these strings can't follow a storefront. */
const COPY: Record<string, {
  title: string; price: string; blurb: string; terms: string; cta: string;
}> = {
  steel_starter_unlock: {
    title: "Starter Unlock",
    price: "$14.99",
    blurb: "10 program builds, plus 5 equipment scans and 7 meal-prep scans to use within 7 days.",
    terms: "One-time purchase. Not a subscription — nothing renews and nothing "
      + "is charged again. Your 10 program builds don't expire. The 5 equipment "
      + "scans and 7 meal-prep scans expire 7 days after purchase or when used "
      + "up, whichever comes first.",
    cta: "Unlock for",
  },
  steel_pro_monthly: {
    title: "Steel Pro",
    price: "$7.99",
    blurb: "Unlimited meal-prep scanning, recipes and program regeneration.",
    // (2) Subscription period + renewal terms, in plain language.
    terms: "Monthly subscription. Payment is charged to your Apple Account at "
      + "confirmation of purchase, and renews automatically every month at the "
      + "same price unless you turn off auto-renew at least 24 hours before the "
      + "period ends. Manage or cancel any time in Settings → your name → "
      + "Subscriptions; cancelling keeps your access until the end of the "
      + "period you've paid for.",
    cta: "Subscribe for",
  },
  steel_equipment_pack_5: {
    title: "5 More Equipment Scans",
    price: "$4.99",
    blurb: "Five more scans of your gym, whenever your setup changes.",
    terms: "One-time purchase. Nothing renews. These scans don't expire.",
    cta: "Buy for",
  },
  steel_program_pack_3: {
    title: "3 More Program Builds",
    price: "$3.99",
    blurb: "Rebuild your program three more times.",
    terms: "One-time purchase. Nothing renews. These builds don't expire.",
    cta: "Buy for",
  },
};

/** Why the paywall appeared, phrased as the thing the user was trying to do. */
const REASON: Record<string, string> = {
  equipment_scan: "You've used your equipment scans.",
  meal_scan: "You've used your meal-prep scans.",
  program_gen: "You've used your program builds.",
};

export default function PaywallScreen({ onClose }: { onClose: () => void }) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const { status, paywall, products, storeReady, purchase, restore } = useBilling();
  const [busy, setBusy] = useState<string | null>(null);
  const [restoring, setRestoring] = useState(false);

  // The 402 names the product to highlight; everything else is still offered
  // below it, because "you must buy exactly this" reads worse than a choice.
  const highlighted = paywall?.product ?? status?.products?.starter ?? "steel_starter_unlock";
  const ordered = useMemo(() => {
    const all = Object.values(status?.products ?? {}).filter((id) => COPY[id]);
    const rest = all.filter((id) => id !== highlighted);
    return [highlighted, ...rest];
  }, [status?.products, highlighted]);

  /** Real localized store price when we have it, else the fallback string. */
  function priceOf(productId: string): string {
    return products[productId]?.priceString ?? COPY[productId]?.price ?? "";
  }

  async function buy(productId: string) {
    setBusy(productId);
    try {
      const done = await purchase(productId);
      if (done) onClose();
    } catch (e) {
      Alert.alert("Purchase didn't go through", friendlyError(e));
    } finally {
      setBusy(null);
    }
  }

  // (3) Restore Purchases — required, and genuinely needed: the starter unlock
  // is non-consumable, so a reinstall or a second device has to get it back.
  async function doRestore() {
    setRestoring(true);
    try {
      await restore();
      Alert.alert("Purchases restored",
        "Anything you've already bought has been re-applied to your account.");
      onClose();
    } catch (e) {
      Alert.alert("Nothing to restore", friendlyError(e));
    } finally {
      setRestoring(false);
    }
  }

  const reason = REASON[paywall?.kind ?? ""] ?? "Unlock scanning to keep going.";

  return (
    <ScreenBackground showHome={false} onBack={onClose} backLabel="Not now">
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title} maxFontSizeMultiplier={1.2}>Keep scanning</Text>
        <Text style={styles.subtitle} maxFontSizeMultiplier={1.4}>{reason}</Text>
        <Text style={styles.body} maxFontSizeMultiplier={1.5}>
          Your program, workout logging, progress and protein tracking stay free.
          Scanning uses AI to recognise your equipment and food, which costs us
          per photo — that's the part these unlock.
        </Text>

        {!storeReady ? (
          <Card>
            <Text style={styles.notice} maxFontSizeMultiplier={1.5}>
              In-app purchases aren't available on this build. Prices below are
              indicative until the App Store connection is live.
            </Text>
          </Card>
        ) : null}

        {ordered.map((productId, index) => {
          const copy = COPY[productId];
          if (!copy) return null;
          return (
            <Card key={productId} style={styles.product}
                  accentColor={index === 0 ? theme.colors.accent : undefined}>
              <View style={styles.productHead}>
                {/* (1) Title + price, before any purchase sheet opens. */}
                <Text style={styles.productTitle} maxFontSizeMultiplier={1.3}>{copy.title}</Text>
                <Text style={styles.price} maxFontSizeMultiplier={1.3}>{priceOf(productId)}</Text>
              </View>
              {index === 0 ? <Badge label="RECOMMENDED" tone="accent" /> : null}
              <Text style={styles.blurb} maxFontSizeMultiplier={1.5}>{copy.blurb}</Text>
              {/* (2) Renewal / expiry terms in plain language. */}
              <Text style={styles.terms} maxFontSizeMultiplier={1.6}>{copy.terms}</Text>
              <Button
                title={`${copy.cta} ${priceOf(productId)}`.trim()}
                onPress={() => buy(productId)}
                loading={busy === productId}
                disabled={busy !== null || restoring}
                variant={index === 0 ? "accent" : "secondary"}
                size={index === 0 ? "large" : "medium"}
              />
            </Card>
          );
        })}

        <View style={styles.footer}>
          <Pressable accessibilityRole="button" onPress={doRestore}
                     disabled={restoring} style={styles.linkBtn}>
            {restoring
              ? <ActivityIndicator color={theme.colors.accent} />
              : <Text style={styles.link} maxFontSizeMultiplier={1.4}>Restore Purchases</Text>}
          </Pressable>

          {/* (4) Terms of Use + Privacy Policy links. */}
          <View style={styles.legalRow}>
            <Pressable accessibilityRole="link" style={styles.linkBtn}
                       onPress={() => Linking.openURL(TERMS_URL)}>
              <Text style={styles.legal} maxFontSizeMultiplier={1.4}>Terms of Use</Text>
            </Pressable>
            <Text style={styles.legal} maxFontSizeMultiplier={1.4}>·</Text>
            <Pressable accessibilityRole="link" style={styles.linkBtn}
                       onPress={() => Linking.openURL(PRIVACY_URL)}>
              <Text style={styles.legal} maxFontSizeMultiplier={1.4}>Privacy Policy</Text>
            </Pressable>
          </View>

          <Text style={styles.legalBody} maxFontSizeMultiplier={1.6}>
            Purchases are charged to your Apple Account. Subscriptions renew
            automatically unless auto-renew is turned off at least 24 hours
            before the end of the current period.
          </Text>
        </View>
      </ScrollView>
    </ScreenBackground>
  );
}

function getStyles(theme: Theme) {
  return StyleSheet.create({
    container: { padding: 20, paddingBottom: 40, gap: 14 },
    title: { ...theme.typography.largeTitle, color: theme.colors.text },
    subtitle: { ...theme.typography.headline, color: theme.colors.accent },
    body: { ...theme.typography.subhead, color: theme.colors.textSecondary },
    notice: { ...theme.typography.footnote, color: theme.colors.warning },
    product: { gap: 10 },
    productHead: { flexDirection: "row", alignItems: "baseline", justifyContent: "space-between", gap: 12 },
    productTitle: { ...theme.typography.title2, color: theme.colors.text, flexShrink: 1 },
    price: { ...theme.typography.title2, color: theme.colors.text },
    blurb: { ...theme.typography.subhead, color: theme.colors.textSecondary },
    terms: { ...theme.typography.footnote, color: theme.colors.textTertiary },
    footer: { marginTop: 6, gap: 10, alignItems: "center" },
    linkBtn: { minHeight: 44, justifyContent: "center", paddingHorizontal: 8 },
    link: { ...theme.typography.headline, color: theme.colors.accent },
    legalRow: { flexDirection: "row", alignItems: "center", gap: 4 },
    legal: { ...theme.typography.footnote, color: theme.colors.secondary },
    legalBody: { ...theme.typography.footnote, color: theme.colors.textTertiary, textAlign: "center" },
  });
}
