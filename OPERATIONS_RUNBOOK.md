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

---

## B. App build → TestFlight

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

## C. Gotchas we actually hit (read before deploying)

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

7. **Reviewer bypass (App Store review):** env vars `REVIEW_EMAIL` + `REVIEW_CODE` on the ECS
   service enable a fixed-code login for `reviewer@glpsteel.com`. **Remove/rotate before public
   launch** — it's a real backdoor for that one account.

8. **Reading logs:**
   ```bash
   aws logs tail "/aws/ecs/default/weightprogram-api-1257-e9c6" --since 5m --region us-east-1 | tail -80
   ```
   The console "Logs" tab truncates long tracebacks; the CLI shows the real final line.

---

## D. Pre-public-launch checklist (open items)
- [ ] Re-enable DB TLS (SSL context in `database.py`; revert `rds.force_ssl`).
- [ ] Remove/rotate the reviewer bypass env vars.
- [ ] Remove diagnostic `_log.warning` lines from `recognition.py`.
- [ ] Give `api.glpsteel.com` a stable route (add it to Express's managed host rule, or a
      dedicated ALB) so the blue/green re-point step goes away.
- [ ] Move DB schema to Alembic migrations (currently `init_models` create_all on boot).
- [ ] App: clear/cap photos in `CaptureScreen`; add keyboard-avoidance in `WorkoutScreen`.
