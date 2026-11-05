// Shared design tokens for the whole app: colors (light + dark), spacing,
// radii, shadows and typography. Everything reads through useTheme() so
// screens automatically follow the system appearance (Dynamic-Type-friendly
// font sizes are handled at the Text level via allowFontScaling defaults).
//
// Palette identity: "gunmetal" — a dark, brushed-steel base (evoking the
// weights themselves) with a warm ember accent and a cool teal secondary for
// variety, instead of a flat monochrome UI.
import { useColorScheme } from "react-native";

export type ThemeColors = {
  background: string;
  backgroundElevated: string;
  backgroundElevated2: string;
  border: string;
  text: string;
  textSecondary: string;
  textTertiary: string;
  textInverted: string;
  accent: string;
  accentSoft: string;
  secondary: string;
  secondarySoft: string;
  success: string;
  successSoft: string;
  danger: string;
  dangerSoft: string;
  warning: string;
  warningSoft: string;
  /** Diagonal gradient stops used behind every screen (see ScreenBackground). */
  gradient: [string, string, string];
};

const light: ThemeColors = {
  background: "#EDEEF1",
  backgroundElevated: "#FFFFFF",
  backgroundElevated2: "#E7E9EC",
  border: "#DBDEE2",
  text: "#1B1D1F",
  textSecondary: "#5B5F64",
  // Darkened from #93989E so small captions/hints clear WCAG AA (4.5:1) on the
  // light backgrounds. See usability review (contrast finding).
  textTertiary: "#70757B",
  textInverted: "#FFFFFF",
  accent: "#E1601E",
  accentSoft: "#FBE7DA",
  secondary: "#0E9488",
  secondarySoft: "#DCF3F0",
  success: "#1F8A3B",
  successSoft: "#E5F7EA",
  danger: "#D70015",
  dangerSoft: "#FDEAEA",
  warning: "#B25000",
  warningSoft: "#FFF3E2",
  gradient: ["#FFFFFF", "#EEF0F2", "#E0E3E6"],
};

const dark: ThemeColors = {
  background: "#111315",
  backgroundElevated: "#2B3136",
  backgroundElevated2: "#383F45",
  border: "#454D53",
  text: "#F5F6F7",
  textSecondary: "#B2B7BC",
  // Lightened from #767C82 for AA on the dark backgrounds (contrast finding).
  textTertiary: "#939AA1",
  textInverted: "#111315",
  accent: "#FF8A50",
  accentSoft: "#4A2E1E",
  secondary: "#2FD9C7",
  secondarySoft: "#173733",
  success: "#3DDC63",
  successSoft: "#173321",
  danger: "#FF5449",
  dangerSoft: "#3D1917",
  warning: "#FFB13D",
  warningSoft: "#3C2A10",
  gradient: ["#3A4147", "#1C1F22", "#0D0F10"],
};

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 28, xxxl: 40 };
export const radius = { sm: 8, md: 12, lg: 16, xl: 22, pill: 999 };

export const typography = {
  largeTitle: { fontSize: 34, fontWeight: "800" as const },
  title: { fontSize: 26, fontWeight: "700" as const },
  title2: { fontSize: 20, fontWeight: "700" as const },
  headline: { fontSize: 17, fontWeight: "600" as const },
  body: { fontSize: 16, fontWeight: "400" as const },
  subhead: { fontSize: 14, fontWeight: "500" as const },
  footnote: { fontSize: 13, fontWeight: "400" as const },
  caption: { fontSize: 11, fontWeight: "700" as const, letterSpacing: 0.4 },
};

export type Theme = {
  colors: ThemeColors;
  dark: boolean;
  spacing: typeof spacing;
  radius: typeof radius;
  typography: typeof typography;
  shadow: { card: Record<string, unknown> };
};

/** Assemble the full Theme object for one appearance mode. */
function build(isDark: boolean): Theme {
  const colors = isDark ? dark : light;
  return {
    colors,
    dark: isDark,
    spacing,
    radius,
    typography,
    shadow: {
      card: isDark
        ? { shadowColor: "#000", shadowOpacity: 0.55, shadowRadius: 14, shadowOffset: { width: 0, height: 6 }, elevation: 5 }
        : { shadowColor: "#1B1D1F", shadowOpacity: 0.08, shadowRadius: 16, shadowOffset: { width: 0, height: 5 }, elevation: 3 },
    },
  };
}

/** Current theme, re-derived whenever the system appearance changes. */
export function useTheme(): Theme {
  const scheme = useColorScheme();
  return build(scheme === "dark");
}
