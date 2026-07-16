# WeightProgram — Operations Runbook

Everything needed to deploy the backend and ship a new app build, plus the gotchas
learned the hard way. Account `453371324700`, region `us-east-1`.

## Key resources
- **API:** https://api.glpsteel.com  (ECS Express service `weightprogram-api-1257`)
- **Gateway ALB:** `ecs-express-gateway-alb-a6344ce9`
- **Target groups (blue/green pair):** `ecs-gateway-tg-daf79a1d189ca3923`, `ecs-gateway-tg-ebf781276206a0a14`
- **ECR repo:** `453371324700.dkr.ecr.us-east-1.amazonaws.com/weightprogram-api`
- **RDS:** `weightprogram-db...rds.amazonaws.com` (Postgres 18, db `postgres`, user `wpadmin`)
- **S3 captures:** `s3://weightprogram-captures`
- **Marketing site:** https://glpsteel.com — `s3://glpsteel-website` + CloudFront (see section F)
- **Log group:** `/aws/ecs/default/weightprogram-api-1257-e9c6`
- **Local build copy:** `~/wp-backend-build` (NOT the exFAT project drive — see gotcha #1)

---

## A. Backend deploy (do this EXACTLY, in order)

```bash
# 1. Edit code in the canonical repo on the drive, THEN sanity-check it parses:
cd "/Volumes/2T_Media/Documents/WeightProgram/WeightProgram/backend"
python3 -m py_compile app/*.py app/routers/*.py && echo COMPILE_OK

# 2. rsync into the internal-disk build copy  (SKIPPING THIS = you rebuild old code)
rsync -a --delete --exclude '.venv' --exclude '__pycache__' --exclude '._*' \
  --exclude '.DS_Store' --exclude '.env' \
  "/Volumes/2T_Media/Documents/WeightProgram/WeightProgram/backend/" ~/wp-backend-build/

# 3. Build (from internal disk) + push
cd ~/wp-backend-build
aws ecr get-login-password --region us-east-1 | docker login --username AWS \
  --password-stdin 453371324700.dkr.ecr.us-east-1.amazonaws.com
docker build --platform linux/amd64 --provenance=false --sbom=false -t weightprogram-api .
docker tag weightprogram-api:latest 453371324700.dkr.ecr.us-east-1.amazonaws.com/weightprogram-api:latest
docker push 453371324700.dkr.ecr.us-east-1.amazonaws.com/weightprogram-api:latest
```

Then in the console:
4. ECS → service `weightprogram-api-1257` → **Update → Force new deployment**.
5. Wait for it to reach steady state. If it **rolls back**, see gotcha #3.
6. **Re-point the custom domain** (blue/green flips the active target group every deploy):
   - EC2 → Target Groups → open both `ecs-gateway-tg-*` → whichever **Targets** tab shows a **healthy** target is the live one.
   - EC2 → Load Balancers → gateway ALB → Listeners → HTTPS:443 → Manage rules → the `api.glpsteel.com` rule → set that healthy target group's weight to **100%**, the other **0%**.
7. Verify: `curl https://api.glpsteel.com/health` → `{"status":"ok","environment":"production"}`.
8. **First deploy with Neutron (nutrition module):** the 7 new tables
   (`nutrition_profiles`, `weight_logs`, `pantry_items`, `saved_recipes`,
   `protein_logs`, `nutrition_badges`, `nutrition_parse_cache` — the last
   added by Voice Log 2026-07-12) are created automatically by
   `init_models` on boot — no manual DB step. Smoke-test with an authed token:
   `GET /nutrition/marketplace` (static data, exercises the router),
   `GET /nutrition/profile` (exercises the new tables), and
   `POST /nutrition/parse` with `{"phrases": ["grilled chicken breast"]}`
   (exercises the voice-log cache + Bedrock text path; call it twice — the
   second response must return `"cached": true`).

---

## B. Local test on the iOS simulator (do this BEFORE every TestFlight push)

The Xcode simulator is set up and working (confirmed 2026-07-06). Never push a build to
Apple that hasn't booted on the simulator first — EAS + review round-trips are too slow
to use as a smoke test.

```bash
cd "/Volumes/2T_Media/Documents/WeightProgram/WeightProgram/mobile"

# 1. Deps in sync (mandatory after any package.json change, e.g. the analytics
#    deps react-native-svg / react-native-view-shot, or the Voice Log deps
#    expo-speech-recognition / expo-sqlite — the latter two are NATIVE +
#    config-plugin deps, so they force a full `npx expo run:ios` rebuild):
npm install

# 2. Typecheck — cheapest possible catch:
npx tsc --noEmit

# 3. Build + launch on the simulator. The app has custom NATIVE deps (Skia, svg,
#    view-shot), so Expo Go can NOT run it — use a dev build:
npx expo run:ios          # first run / after any native-dep change (slow: full Xcode build)
npx expo start            # subsequent JS-only changes: reuse the installed dev build
```

- **Backend target:** `src/config.ts` points at production (`https://api.glpsteel.com`) —
  fine for UI testing against real data. To test *backend* changes locally instead, run
  `uvicorn app.main:app --reload` in `backend/` and switch `config.ts` to the localhost
  line (simulator reaches the Mac's localhost directly). **Switch it back before building.**
- **Login without email round-trips:** the reviewer bypass works on the simulator —
  `reviewer@glpsteel.com` / code `027858`.
- **What to check before pushing:** app boots, every screen you touched renders in BOTH
  light and dark mode, and (if native deps changed) the affected views actually draw —
  the Skia blank-screen incident (gotcha #9) is exactly the failure class the simulator
  catches that typecheck can't.
- **If the native build fails with `._*` / permission weirdness:** that's the exFAT drive
  again (gotcha #1's sibling). Mirror the backend trick — rsync `mobile/` to an
  internal-disk copy and run `npx expo run:ios` from there.

Only when the simulator pass is clean, proceed to section C.

---

## C. App build → TestFlight

```bash
cd "/Volumes/2T_Media/Documents/WeightProgram/WeightProgram/mobile"
# bump ios.buildNumber in app.json first (must be unique per upload)
npx eas-cli build --platform ios --profile production
npx eas-cli submit --platform ios --latest
```
Then App Store Connect → TestFlight → the build appears after processing.
Internal testers install immediately; external group needs one-time Beta App Review.
After a dependency change, always `npx expo start -c` locally (stale-bundle trap).

---

## D. Gotchas we actually hit (read before deploying)

1. **Build from `~/wp-backend-build`, never the exFAT drive.** `/Volumes/2T_Media` is exFAT;
   macOS `._*` AppleDouble files break `docker build` (`operation not permitted`). Always
   rsync to the internal disk and build there. And **re-run the rsync after EVERY edit** —
   forgetting it means you rebuild the old code (this bit us 3×).

2. **`--provenance=false --sbom=false` on docker build.** Otherwise buildx pushes an OCI
   image index + attestations that Fargate intermittently can't pull (`ref ... not found`).

3. **Rollback / circuit breaker on deploy** = the new task failed to become healthy. Check the
   newest **stopped task**:
   - "Essential container exited" → code crash on boot. Read the log group; usually an
     ImportError/indentation slip from a hand-edit. Fix, rsync, rebuild.
   - "Task failed ELB health checks" → the new target group's health-check **path reset to `/`**.
     Set BOTH target groups' health-check path to **`/health`**, redeploy.

4. **Blue/green re-point (step A6) after every deploy** — the `api.glpsteel.com` listener rule
   must forward 100% to whichever target group currently holds the healthy task. Symptom if
   skipped: `/health` on the `.on.aws` URL works but `api.glpsteel.com` returns 503.

5. **DB / RDS:**
   - RDS requires TLS by default; we set parameter group `rds.force_ssl=0` so asyncpg connects
     without SSL. (TODO: re-enable TLS via an SSL context in `database.py` before public launch.)
   - Master password must be **URL-safe** (letters+digits only) — it goes into `DATABASE_URL`;
     `@ : / #` break the connection string.
   - The real password lives in the ECS task-def env var `DATABASE_URL`, not any note.

6. **Recognition / images:**
   - The backend caps to the first **4 images** (`image_bytes[:4]` in `recognition.py`) — Bedrock
     silently returns 0 items if the combined image payload is too large. Keep this cap.
   - The app must send **JPEG** (iOS shoots HEIC, which Bedrock can't read) — `CaptureScreen`
     re-encodes via `expo-image-manipulator`.
   - `BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-6` (inference-profile id, not bare model id).
   - **Neutron reuses all of the above:** the pantry scanner (`neutron_vision.py`) has the
     same 4-image cap and JPEG requirement (KitchenScanScreen re-encodes like CaptureScreen).
     The recipe engine (`neutron_recipes.py`) is **text-only** Converse on the same model id —
     no extra Bedrock access needed. **Both Neutron Bedrock paths enforce a maxTokens floor of
     4096** (pantry scans return 20-40 items, recipes are long; below that the forced tool call
     truncates mid-JSON and parses to 0 items — symptom: scan "finds nothing" / recipes 502).
     An empty pantry parse logs `pantry scan parsed 0 items: stopReason=...` — check with the
     log-tail command in gotcha #8. Recipes run at temperature 0.7 (variety), vision stays at 0.
   - **Local dev without AWS:** `VISION_PROVIDER=stub` also selects the stub pantry scanner and
     stub recipe engine, so the whole scan → recipes → log flow works offline.

7. **Reviewer bypass (App Store review):** env vars `REVIEW_EMAIL` + `REVIEW_CODE` on the ECS
   service enable a fixed-code login for `reviewer@glpsteel.com`. **Remove/rotate before public
   launch** — it's a real backdoor for that one account.

8. **Reading logs:**
   ```bash
   aws logs tail "/aws/ecs/default/weightprogram-api-1257-e9c6" --since 5m --region us-east-1 | tail -80
   ```
   The console "Logs" tab truncates long tracebacks; the CLI shows the real final line.

9. **Skia renders blank on-device.** `@shopify/react-native-skia` drew nothing (blank white
   screen) on iPhone 16 / iOS 26 and was backed out of `ScreenBackground`; never root-caused.
   It's still in `package.json` but must be treated as quarantined — don't build UI on it.
   Charts and the PR share card deliberately use `react-native-svg` + `react-native-view-shot`
   instead. Any new drawing/canvas work: same substrate, and verify on the simulator (section B)
   before pushing.

10. **app.json config plugins DON'T apply to EAS builds — this is a bare project.**
    `mobile/ios/` exists (created by `expo run:ios`), so EAS builds the native
    project as-is and never runs prebuild; plugin entries in `app.json` (e.g.
    permission strings) silently do nothing. This caused the ITMS-90683
    rejection of Build 11 (missing `NSSpeechRecognitionUsageDescription` for
    Voice Log — fixed 2026-07-12 by editing `ios/WeightProgram/Info.plist`
    directly). Rule: any new iOS permission/entitlement/plugin setting must be
    added to `ios/WeightProgram/Info.plist` (or the Xcode project) by hand.
    Keep the `app.json` plugin entries anyway — they're the source of truth if
    the `ios/` folder is ever regenerated with `npx expo prebuild --clean`
    (which otherwise OVERWRITES hand edits — re-check Info.plist after any
    prebuild).

---

## E. Pre-public-launch checklist (open items)
- [ ] Re-enable DB TLS (SSL context in `database.py`; revert `rds.force_ssl`).
- [ ] Remove/rotate the reviewer bypass env vars.
- [ ] Remove diagnostic `_log.warning` lines from `recognition.py`.
- [ ] Give `api.glpsteel.com` a stable route (add it to Express's managed host rule, or a
      dedicated ALB) so the blue/green re-point step goes away.
- [ ] Move DB schema to Alembic migrations (currently `init_models` create_all on boot).
- [ ] App: clear/cap photos in `CaptureScreen`; add keyboard-avoidance in `WorkoutScreen`.
- [ ] Neutron: swap the marketplace placeholder URLs in `routers/nutrition.py`
      (`_MARKETPLACE`) for real affiliate links and re-check the disclosure copy;
      re-verify product prices/protein before launch.
- [ ] Neutron: privacy policy in `main.py` mentions equipment photos only — add a line
      covering kitchen-scan photos (processed for recognition, never stored) before launch.
- [ ] Website: replace placeholders before launch — store links (`href="#"`), fake
      ratings/press bar, placeholder testimonials, `og:image`. Full list in
      `website/WEBSITE_BRIEF.md`. Don't publish while nutrition scan is unshipped.

---

## F. Marketing website deploy (glpsteel.com)

Source: `website/index.html` (single self-contained file). Hosted on S3 + CloudFront,
DNS via the existing Route 53 zone (apex + `www` alias A records → CloudFront).

```bash
# Update the live site after editing website/index.html:
aws s3 cp "/Volumes/2T_Media/Documents/WeightProgram/WeightProgram/website/index.html" \
  s3://glpsteel-website/index.html --content-type text/html
aws cloudfront create-invalidation --distribution-id DIST_ID_HERE --paths "/*"
```

- **Fill in `DIST_ID_HERE`** once: CloudFront console → the glpsteel.com distribution → ID
  (starts with `E`), then replace the placeholder in this file.
- The invalidation is required — CloudFront caches `index.html`, so without it edits can
  take up to 24h to appear. Invalidations take ~1–2 min; first 1,000 paths/month are free.
- Bucket is private (CloudFront OAC); don't add a public bucket policy.
- ACM cert for glpsteel.com/www lives in us-east-1 (required by CloudFront).

---

## G. Push project to GitHub

Repo: https://github.com/kopiluwak/RetaWeightProgram (remote `origin`, branch `main`).

```bash
cd "/Volumes/2T_Media/Documents/WeightProgram/WeightProgram"
git add -A
git commit -m "describe the change"
git push origin main
```
