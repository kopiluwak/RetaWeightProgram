#!/usr/bin/env bash
# new-mac-check.sh — read-only health check for the WeightProgram toolchain
# on a fresh Mac. Changes nothing. Run:
#   bash "/Volumes/2T_Media/Documents/WeightProgram/WeightProgram/scripts/new-mac-check.sh"
# then paste the whole output back to Claude.

ROOT="/Volumes/2T_Media/Documents/WeightProgram/WeightProgram"
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.docker/bin:$PATH"
FAILS=()

ok()   { printf '  \033[32mOK\033[0m   %s\n' "$*"; }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAILS+=("$1  →  $2"); }
info() { printf '       %s\n' "$*"; }
hdr()  { printf '\n== %s\n' "$*"; }

hdr "Machine"
info "macOS $(sw_vers -productVersion) ($(uname -m)), user $(whoami), host $(scutil --get LocalHostName 2>/dev/null)"
[ -d "$ROOT" ] && ok "project drive mounted at $ROOT" || bad "project folder not found at $ROOT" "check the drive is mounted as 2T_Media"
info "drive format: $(diskutil info /Volumes/2T_Media 2>/dev/null | awk -F: '/File System Personality/{gsub(/^ +/,"",$2);print $2}')"

hdr "Xcode / iOS"
if xcode-select -p 2>/dev/null | grep -q Xcode.app; then
  ok "xcode-select → $(xcode-select -p)"
  info "$(xcodebuild -version 2>&1 | tr '\n' ' ')"
  if xcodebuild -checkFirstLaunchStatus >/dev/null 2>&1; then ok "first-launch components installed"
  else bad "Xcode first-launch not finished" "sudo xcodebuild -runFirstLaunch"; fi
  if xcrun simctl list runtimes 2>/dev/null | grep -q '^iOS'; then
    ok "simulator runtime(s): $(xcrun simctl list runtimes | grep '^iOS' | awk '{print $2}' | tr '\n' ' ')"
  else bad "no iOS simulator runtime" "Xcode → Settings → Components → install an iOS simulator"; fi
else
  bad "full Xcode not selected (got: $(xcode-select -p 2>&1))" "install Xcode from the App Store, then: sudo xcode-select -s /Applications/Xcode.app && sudo xcodebuild -license accept"
fi

hdr "Command-line tools"
chk() { # name, fix
  if command -v "$1" >/dev/null 2>&1; then ok "$1 $("$1" --version 2>&1 | head -1)"; else bad "$1 missing" "$2"; fi
}
chk brew     '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
chk node     'brew install node@20 && brew link --overwrite node@20'
chk npm      'comes with node'
chk git      'xcode-select --install'
chk pod      'brew install cocoapods'
chk fastlane 'brew install fastlane   (only needed for local EAS builds, runbook §C2)'
chk watchman 'brew install watchman   (optional, faster Metro)'
chk python3  'brew install python@3.12'
if ! command -v docker >/dev/null 2>&1 && [ -x /Applications/Docker.app/Contents/Resources/bin/docker ]; then
  bad "Docker Desktop is installed but its docker command isn't on your PATH" "open -a Docker, finish its setup; then Docker Settings → Advanced → choose 'System (requires password)', Apply & restart. Or: echo 'export PATH=\"\$PATH:/Applications/Docker.app/Contents/Resources/bin\"' >> ~/.zprofile"
  export PATH="$PATH:/Applications/Docker.app/Contents/Resources/bin"
fi
chk docker   'install Docker Desktop for Apple silicon (from docker.com), then open it once'

chk aws      'brew install awscli && aws configure   (region us-east-1)'
if command -v node >/dev/null; then
  NV=$(node -p 'process.versions.node.split(".")[0]')
  [ "$NV" -ge 20 ] && [ "$NV" -le 22 ] && ok "node major $NV is fine for Expo SDK 54" || bad "node major $NV — Expo SDK 54 wants 20 or 22" "brew install node@20 && brew link --overwrite node@20"
fi

hdr "Accounts / credentials"
if command -v docker >/dev/null; then docker info >/dev/null 2>&1 && ok "Docker daemon running" || bad "Docker installed but not running" "open -a Docker"; fi
if command -v aws >/dev/null; then
  ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
  [ "$ID" = "453371324700" ] && ok "AWS CLI signed in to account 453371324700" || bad "AWS CLI not signed in to 453371324700 (got '${ID:-none}')" "aws configure  (access key for account 453371324700, region us-east-1)"
fi
EASU=$(cd "$ROOT/mobile" 2>/dev/null && npx --yes eas-cli whoami 2>/dev/null | head -1)
[ -n "$EASU" ] && ! echo "$EASU" | grep -qi 'not logged' && ok "EAS signed in as $EASU" || bad "EAS not signed in" "cd mobile && npx eas-cli login"
git -C "$ROOT" config user.email >/dev/null && ok "git identity $(git -C "$ROOT" config user.name) <$(git -C "$ROOT" config user.email)>" || bad "git identity not set" 'git config --global user.name "…" && git config --global user.email "…"'
git -C "$ROOT" ls-remote origin HEAD >/dev/null 2>&1 && ok "GitHub remote reachable (origin)" || bad "can't reach GitHub origin" "gh auth login   (or set up an SSH key / credential helper)"

hdr "Project"
cd "$ROOT/mobile" 2>/dev/null || exit 1
if [ -f node_modules/react-native/package.json ]; then ok "mobile/node_modules present (RN $(node -p 'require("./node_modules/react-native/package.json").version' 2>/dev/null))"
else bad "mobile/node_modules missing" "cd mobile && npm install"; fi
npx --no-install tsc --noEmit >/tmp/wp-tsc.txt 2>&1 && ok "mobile typecheck clean" || bad "mobile typecheck failed (see /tmp/wp-tsc.txt)" "paste /tmp/wp-tsc.txt to Claude"
[ -d ios/Pods ] && ok "ios/Pods present" || bad "ios/Pods missing" "cd mobile/ios && pod install"
if command -v pod >/dev/null && [ -f ios/Podfile.lock ]; then
  (cd ios && pod check >/dev/null 2>&1) && ok "Pods in sync with Podfile.lock" || info "pods may need refresh: cd mobile/ios && pod install"
fi
grep -q 'api.glpsteel.com' src/config.ts && ! grep -q '^export const API_BASE_URL = "http://' src/config.ts && ok "config.ts points at production API" || bad "config.ts not pointing at https://api.glpsteel.com" "switch the export back before building"
[ -d "$HOME/wp-backend-build" ] && ok "~/wp-backend-build exists" || bad "~/wp-backend-build missing (needed for docker builds off the exFAT drive)" "runbook §A step 2 rsync creates it"
CODE=$(curl -s -m 10 https://api.glpsteel.com/health)
echo "$CODE" | grep -q '"ok"' && ok "prod API: $CODE" || bad "prod API /health not ok: '${CODE:-no response}'" "check ECS service + listener rule (runbook gotcha #4)"
for p in /billing/status /programs/couch /me/deletion; do
  info "prod $p → HTTP $(curl -s -m 10 -o /dev/null -w '%{http_code}' https://api.glpsteel.com$p)  (401 or 405 = route deployed, 404 = not deployed yet)"
done

hdr "Summary"
if [ ${#FAILS[@]} -eq 0 ]; then echo "  All checks passed."; else
  printf '  %d item(s) to fix:\n' "${#FAILS[@]}"; for f in "${FAILS[@]}"; do echo "   - $f"; done; fi
