// Neutron: Protein Boosters marketplace.
// Curated high-protein products with per-serving protein, price, GLP-1 fit
// tags, and clearly-labeled placeholder affiliate links + commission disclosure.
import React, { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Alert, Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { MarketItem, NutritionApi } from "../api";
import { Theme, useTheme } from "../theme";
import { Badge, Button, Card, Chip, ScreenBackground } from "../ui";

const CATEGORY_LABELS: Record<string, string> = {
  all: "All",
  protein_powder: "Powders",
  ready_to_drink: "Shakes",
  bar: "Bars",
  dairy: "Dairy",
  ready_to_eat: "Ready to eat",
  snack: "Snacks",
};

export default function ProteinBoostersScreen({ onBack }: { onBack: () => void }) {
  const theme = useTheme();
  const styles = useMemo(() => getStyles(theme), [theme]);
  const [items, setItems] = useState<MarketItem[]>([]);
  const [disclosure, setDisclosure] = useState("");
  const [category, setCategory] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    NutritionApi.marketplace()
      .then((m) => {
        setItems(m.items);
        setDisclosure(m.disclosure);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const categories = useMemo(
    () => ["all", ...Array.from(new Set(items.map((i) => i.category)))],
    [items]
  );
  const visible = category === "all" ? items : items.filter((i) => i.category === category);

  function open(item: MarketItem) {
    if (item.url_is_placeholder) {
      Alert.alert(
        "Placeholder link",
        "Affiliate partnerships aren't live yet — this link is a placeholder. The product info is real, so you can find it at any major retailer."
      );
      return;
    }
    Linking.openURL(item.url).catch(() => {});
  }

  return (
    <ScreenBackground onBack={onBack} backLabel="Nutrition">
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title} maxFontSizeMultiplier={1.2}>Protein Boosters</Text>
        <Text style={styles.subtitle} maxFontSizeMultiplier={1.4}>
          When appetite is small, convenience wins. These picks pack the most protein into the
          fewest, easiest bites.
        </Text>

        {loading ? (
          <ActivityIndicator size="large" color={theme.colors.text} style={{ marginTop: 60 }} />
        ) : error ? (
          <Text style={styles.error} maxFontSizeMultiplier={1.4}>{error}</Text>
        ) : (
          <>
            {/* Disclosure sits ABOVE the products on purpose. The FTC's
                clear-and-conspicuous test weighs proximity and placement, and
                treats a disclosure buried after a list of items — or at the
                end of a scroll — as insufficient. It has to be unavoidable
                before the first endorsement, not findable after the last. */}
            <Text style={styles.disclosure} maxFontSizeMultiplier={1.6}>{disclosure}</Text>

            <View style={styles.chipRow}>
              {categories.map((c) => (
                <Chip key={c} label={CATEGORY_LABELS[c] ?? c} selected={category === c}
                  onPress={() => setCategory(c)} />
              ))}
            </View>

            {visible.map((item, i) => (
              <Card key={i} style={{ gap: 8 }}>
                <View style={styles.rowBetween}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.itemName} maxFontSizeMultiplier={1.3}>{item.name}</Text>
                    <Text style={styles.brand} maxFontSizeMultiplier={1.5}>{item.brand}</Text>
                  </View>
                  <Text style={styles.price} maxFontSizeMultiplier={1.3}>${item.price_usd.toFixed(2)}</Text>
                </View>
                <View style={styles.badgeRow}>
                  <Badge label={`${Math.round(item.protein_per_serving_g)} g / ${item.serving}`} tone="success" />
                  {item.tags.map((t) => (
                    <Badge key={t} label={t} tone={t.toLowerCase().includes("glp-1") ? "accent" : "neutral"} />
                  ))}
                </View>
                <Button
                  title={item.url_is_placeholder ? "View product (placeholder link)" : "View product"}
                  size="medium" variant="secondary" onPress={() => open(item)}
                />
              </Card>
            ))}
          </>
        )}
      </ScrollView>
    </ScreenBackground>
  );
}

function getStyles(theme: Theme) {
  return StyleSheet.create({
    container: { padding: 20, gap: 14, paddingBottom: 40 },
    backText: { ...theme.typography.headline, color: theme.colors.accent },
    title: { ...theme.typography.title, color: theme.colors.text },
    subtitle: { ...theme.typography.subhead, color: theme.colors.textSecondary, lineHeight: 20 },
    chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
    rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 10 },
    itemName: { ...theme.typography.headline, color: theme.colors.text },
    brand: { ...theme.typography.footnote, color: theme.colors.textSecondary, marginTop: 1 },
    price: { ...theme.typography.title2, color: theme.colors.accent },
    badgeRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
    error: { ...theme.typography.subhead, color: theme.colors.danger },
    disclosure: {
      ...theme.typography.footnote, color: theme.colors.textTertiary,
      textAlign: "center", marginTop: 6, lineHeight: 17,
    },
  });
}
