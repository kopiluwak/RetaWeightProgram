import React, { useRef, useState } from "react";
import { Animated, Easing, Modal, Pressable, StyleSheet, Text, View } from "react-native";
import * as Haptics from "expo-haptics";
import { useTheme } from "../theme";

export type MenuItem = {
  label: string;
  onPress: () => void;
  destructive?: boolean;
  disabled?: boolean;
};

/**
 * A compact, anchored popover menu in the style of iOS's UIMenu: tap the
 * trigger, the menu springs in from the top-right with a slight overshoot,
 * tapping anywhere outside (or an item) dismisses it. Rendered in a native
 * Modal so it always sits above scrolling content regardless of where the
 * trigger lives in the tree.
 */
export default function OverflowMenu({
  trigger,
  items,
}: {
  trigger: (open: () => void, isOpen: boolean) => React.ReactNode;
  items: MenuItem[];
}) {
  const theme = useTheme();
  const [visible, setVisible] = useState(false);
  const [anchorTop, setAnchorTop] = useState(0);
  const anim = useRef(new Animated.Value(0)).current;
  const triggerRef = useRef<View>(null);

  function open() {
    triggerRef.current?.measureInWindow((_x, y, _width, height) => {
      setAnchorTop(y + height + 6);
      setVisible(true);
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
      anim.setValue(0);
      Animated.spring(anim, { toValue: 1, useNativeDriver: true, speed: 24, bounciness: 7 }).start();
    });
  }

  function close(after?: () => void) {
    Animated.timing(anim, {
      toValue: 0,
      duration: 130,
      easing: Easing.out(Easing.quad),
      useNativeDriver: true,
    }).start(() => {
      setVisible(false);
      after?.();
    });
  }

  const scale = anim.interpolate({ inputRange: [0, 1], outputRange: [0.86, 1] });
  const translateY = anim.interpolate({ inputRange: [0, 1], outputRange: [-8, 0] });

  return (
    <>
      <View ref={triggerRef} collapsable={false}>
        {trigger(open, visible)}
      </View>
      <Modal visible={visible} transparent animationType="none" statusBarTranslucent onRequestClose={() => close()}>
        <Pressable style={StyleSheet.absoluteFill} onPress={() => close()} accessibilityLabel="Dismiss menu" />
        <Animated.View
          pointerEvents={visible ? "auto" : "none"}
          style={[
            styles.menu,
            {
              top: anchorTop,
              backgroundColor: theme.colors.backgroundElevated,
              borderColor: theme.colors.border,
              opacity: anim,
              transform: [{ scale }, { translateY }],
            },
            theme.shadow.card,
          ]}
        >
          {items.map((it, i) => (
            <Pressable
              key={it.label}
              disabled={it.disabled}
              onPress={() => {
                Haptics.selectionAsync().catch(() => {});
                close(it.onPress);
              }}
              style={({ pressed }) => [
                styles.item,
                i < items.length - 1 && { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: theme.colors.border },
                pressed && { backgroundColor: theme.colors.backgroundElevated2 },
                it.disabled && { opacity: 0.4 },
              ]}
            >
              <Text
                style={[styles.itemText, { color: it.destructive ? theme.colors.danger : theme.colors.text }]}
                maxFontSizeMultiplier={1.4}
              >
                {it.label}
              </Text>
            </Pressable>
          ))}
        </Animated.View>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  menu: {
    position: "absolute",
    right: 20,
    minWidth: 220,
    borderRadius: 16,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: "hidden",
  },
  item: { paddingVertical: 14, paddingHorizontal: 18 },
  itemText: { fontSize: 15.5, fontWeight: "600" },
});
