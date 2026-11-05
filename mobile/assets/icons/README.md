# App Icons

Generated from `icon-source.png` (kettlebell-focused square crop of the gym photo).

## Files

| File | Purpose |
|---|---|
| `icon.png` | 1024×1024 master, referenced by `expo.icon` in app.json (also used for Android fallback) |
| `ios-light.png` | Default iOS icon (`expo.ios.icon.light`) |
| `ios-dark.png` | iOS 18 Dark appearance (`expo.ios.icon.dark`) |
| `ios-tinted.png` | iOS 18 Tinted appearance — grayscale, system applies tint (`expo.ios.icon.tinted`) |
| `legacy-sizes/` | Per-device sizes (Icon-20@2x…Icon-1024). NOT required — Xcode 14+ uses a single 1024px "Single Size" icon. Kept for reference/other tooling. |

## Legacy size list (for reference)

Icon-20@2x (40), Icon-20@3x (60), Icon-29@2x (58), Icon-29@3x (87),
Icon-40@2x (80), Icon-40@3x (120), Icon-60@2x (120), Icon-60@3x (180),
Icon-76@2x (152, iPad), Icon-83.5@2x (167, iPad Pro), Icon-1024 (App Store).

## How it's wired

1. **Expo (source of truth):** `app.json` → `expo.icon` + `expo.ios.icon.{light,dark,tinted}`. Any `npx expo prebuild` regenerates the native icon set from these.
2. **Xcode (already applied directly):** `ios/WeightProgram/Images.xcassets/AppIcon.appiconset/` contains all three 1024px PNGs with `appearances` entries in Contents.json (Xcode 15+/iOS 18 format). Open the workspace and the AppIcon set shows Any/Dark/Tinted slots filled.

## Export settings used

PNG, sRGB, RGB (no alpha — App Store rejects transparency in the main icon), square 1024×1024, no pre-rounded corners (iOS applies its own mask). Light variant: +6% brightness, +5% contrast, unsharp mask for small-size legibility. Dark: −12% brightness, +10% contrast. Tinted: autocontrast grayscale.

## Rebuild to see it

```bash
cd mobile
eas build --platform ios --profile <your-profile>
# or locally: npx expo run:ios
```

Icon changes require a new build — they don't apply via OTA updates.

## SwiftUI preview snippet (if you add native Swift UI)

```swift
struct AppIconPreview: View {
    var body: some View {
        Image(uiImage: UIImage(named: "AppIcon") ?? UIImage())
            .resizable()
            .scaledToFit()
            .frame(width: 120, height: 120)
            .clipShape(RoundedRectangle(cornerRadius: 27, style: .continuous))
            .shadow(radius: 4)
    }
}
```

## React Native equivalent (for a settings screen in this app)

```tsx
import { Image } from 'react-native';

<Image
  source={require('../../assets/icons/icon.png')}
  style={{ width: 120, height: 120, borderRadius: 27 }}
/>
```
