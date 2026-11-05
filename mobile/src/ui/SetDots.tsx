import React from "react";
import { View } from "react-native";
import { useTheme } from "../theme";

/**
 * Small row of dots representing every set of an exercise: filled/green for
 * done, a larger accent ring for the set the user is on right now, and a
 * dim dot for sets not yet reached. This is the at-a-glance answer to
 * "which set am I on for this exercise".
 */
export default function SetDots({ total, completed, current }: { total: number; completed: number; current: number }) {
  const theme = useTheme();
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 7 }}>
      {Array.from({ length: total }).map((_, i) => {
        const done = i < completed;
        const isCurrent = i === current && !done;
        const size = isCurrent ? 13 : 9;
        return (
          <View
            key={i}
            style={{
              width: size,
              height: size,
              borderRadius: size / 2,
              backgroundColor: done ? theme.colors.success : isCurrent ? theme.colors.accent : theme.colors.backgroundElevated2,
              borderWidth: isCurrent ? 3 : 0,
              borderColor: theme.colors.accentSoft,
            }}
          />
        );
      })}
    </View>
  );
}
