#!/usr/bin/env bash
# sim-build.sh — one-shot: toolchain check → deps → typecheck → pods → Xcode
# simulator build → install → Metro + launch. Implements runbook §B + gotcha #13
# (Xcode 27: `npx expo run:ios` is broken, so build by hand).
# Run:  bash "/Volumes/2T_Media/Documents/WeightProgram/WeightProgram/scripts/sim-build.sh"
# Everything is logged to build-logs/ so Claude can read the result.
ROOT="/Volumes/2T_Media/Documents/WeightProgram/WeightProgram"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
SIM="${SIM:-iPhone 17}"
LOGDIR="$ROOT/build-logs"; mkdir -p "$LOGDIR"
LOG="$LOGDIR/sim-build.log"; XLOG="$LOGDIR/xcodebuild.log"
: > "$LOG"
step() { printf '\n===== %s  (%s)\n' "$*" "$(date '+%H:%M:%S')" | tee -a "$LOG"; }
run()  { "$@" 2>&1 | tee -a "$LOG"; return "${PIPESTATUS[0]}"; }
die()  { printf '\nRESULT: FAILED at: %s\n' "$*" | tee -a "$LOG"; exit 1; }

step "1/8 toolchain check"
run bash "$ROOT/scripts/new-mac-check.sh"

step "2/8 git"
run git -C "$ROOT" fetch origin
run git -C "$ROOT" status -sb

cd "$ROOT/mobile" || die "cd mobile"
step "3/8 npm install"
run npm install || die "npm install"

step "4/8 Expo SDK dependency check (informational)"
run npx expo install --check </dev/null || true
run npx --yes expo-doctor </dev/null || true

step "5/8 typecheck"
run npx tsc --noEmit || die "tsc"

step "6/8 pod install"
(cd ios && run pod install) || die "pod install"

step "7/8 xcodebuild (Debug, simulator: $SIM) — full log in build-logs/xcodebuild.log"
xcrun simctl boot "$SIM" 2>&1 | tee -a "$LOG"
open /Applications/Xcode.app/Contents/Applications/DeviceHub.app 2>/dev/null || open -a Simulator 2>/dev/null
xcodebuild -workspace ios/WeightProgram.xcworkspace -scheme WeightProgram -configuration Debug \
  -sdk iphonesimulator -destination "platform=iOS Simulator,name=$SIM" \
  -derivedDataPath "$HOME/wp-derived" build > "$XLOG" 2>&1
XRC=$?
grep -E "error:|BUILD (SUCCEEDED|FAILED)" "$XLOG" | sort -u | tail -40 | tee -a "$LOG"
[ $XRC -eq 0 ] || die "xcodebuild (exit $XRC)"

step "8/8 install + launch"
run xcrun simctl install booted "$HOME/wp-derived/Build/Products/Debug-iphonesimulator/WeightProgram.app" || die "simctl install"
printf '\nRESULT: BUILD + INSTALL OK\n' | tee -a "$LOG"
echo "Starting Metro (leave this window open; Ctrl-C to stop)…"
( sleep 15; xcrun simctl launch booted com.weightprogram.app 2>&1 | tee -a "$LOG" ) &
npx expo start --dev-client
