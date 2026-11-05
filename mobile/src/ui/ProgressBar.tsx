// Horizontal progress bar with a springless width animation.
import React, { useEffect, useRef } from "react";
import { Animated, View } from "react-native";
import { useTheme } from "../theme";

/** Animated fill bar; progress is clamped to 0..1 before animating. */
export default function ProgressBar({
  progress,
  color,
  trackColor,
  height = 8,
}: {
  /** 0..1 */
  progress: number;
  color?: string;
  trackColor?: string;
  height?: number;
}) {
  const theme = useTheme();
  const anim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(anim, {
      toValue: Math.max(0, Math.min(1, progress)),
      duration: 320,
      useNativeDriver: false,
    }).start();
  }, [progress, anim]);

  const width = anim.interpolate({ inputRange: [0, 1], outputRange: ["0%", "100%"] });

  return (
    <View
      style={{
        height,
        borderRadius: height / 2,
        backgroundColor: trackColor ?? theme.colors.backgroundElevated2,
        overflow: "hidden",
      }}
    >
      <Animated.View
        style={{
          width,
          height,
          borderRadius: height / 2,
          backgroundColor: color ?? theme.colors.accent,
        }}
      />
    </View>
  );
}
