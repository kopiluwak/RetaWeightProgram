import React from "react";
import { View } from "react-native";
import { useTheme } from "../theme";

// Small hand-built glyphs (no icon/vector library is installed in this project).
// Each is a handful of Views composed into a simple, crisp silhouette that reads
// clearly at small sizes and follows the current theme color.

export function IconBadge({ children, tint, size = 44 }: { children: React.ReactNode; tint?: string; size?: number }) {
  const theme = useTheme();
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size * 0.32,
        backgroundColor: tint ?? theme.colors.backgroundElevated2,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {children}
    </View>
  );
}

/** A minimal barbell silhouette: a thin bar with a plate weighted at each end. */
export function DumbbellGlyph({ color }: { color: string }) {
  return (
    <View style={{ width: 28, height: 20, alignItems: "center", justifyContent: "center" }}>
      <View style={{ position: "absolute", width: 28, height: 3, borderRadius: 2, backgroundColor: color }} />
      <View style={{ position: "absolute", left: 0, width: 8, height: 20, borderRadius: 4, backgroundColor: color }} />
      <View style={{ position: "absolute", right: 0, width: 8, height: 20, borderRadius: 4, backgroundColor: color }} />
    </View>
  );
}

/** A simple plate + fork mark, standing in for nutrition until that feature ships. */
export function NutritionGlyph({ color }: { color: string }) {
  return (
    <View style={{ width: 26, height: 26, alignItems: "center", justifyContent: "center" }}>
      <View
        style={{
          width: 24,
          height: 24,
          borderRadius: 12,
          borderWidth: 2.75,
          borderColor: color,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <View style={{ width: 7, height: 7, borderRadius: 3.5, backgroundColor: color }} />
      </View>
    </View>
  );
}

/** Vertical three-dot "more" affordance for the top-right overflow menu. */
export function DotsGlyph({ color }: { color: string }) {
  return (
    <View style={{ width: 22, height: 22, alignItems: "center", justifyContent: "center", gap: 3.5 }}>
      {[0, 1, 2].map((i) => (
        <View key={i} style={{ width: 4.5, height: 4.5, borderRadius: 2.25, backgroundColor: color }} />
      ))}
    </View>
  );
}

/** Right-facing chevron built from a rotated square corner — used as a row affordance. */
export function ChevronGlyph({ color }: { color: string }) {
  return (
    <View
      style={{
        width: 8,
        height: 8,
        borderTopWidth: 2,
        borderRightWidth: 2,
        borderColor: color,
        transform: [{ rotate: "45deg" }],
      }}
    />
  );
}

/** A simple house silhouette (roof triangle + body) for the Home tab. */
export function HomeGlyph({ color }: { color: string }) {
  return (
    <View style={{ width: 24, height: 22, alignItems: "center", justifyContent: "flex-end" }}>
      <View
        style={{
          width: 0,
          height: 0,
          borderLeftWidth: 12,
          borderRightWidth: 12,
          borderBottomWidth: 10,
          borderLeftColor: "transparent",
          borderRightColor: "transparent",
          borderBottomColor: color,
        }}
      />
      <View
        style={{
          width: 16,
          height: 11,
          backgroundColor: color,
          marginTop: -1,
          borderBottomLeftRadius: 2,
          borderBottomRightRadius: 2,
        }}
      />
    </View>
  );
}

/** A rising three-bar mini chart — the Progress entry point on Home. */
export function TrendGlyph({ color }: { color: string }) {
  return (
    <View style={{ width: 26, height: 22, flexDirection: "row", alignItems: "flex-end", justifyContent: "center", gap: 3 }}>
      <View style={{ width: 5.5, height: 9, borderRadius: 2, backgroundColor: color }} />
      <View style={{ width: 5.5, height: 15, borderRadius: 2, backgroundColor: color }} />
      <View style={{ width: 5.5, height: 21, borderRadius: 2, backgroundColor: color }} />
    </View>
  );
}
