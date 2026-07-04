# Deploying WeightProgram backend to AWS (api.glpsteel.com)

Target architecture (all in `us-east-1`, account `453371324700`):

```
Phone (TestFlight)  →  https://api.glpsteel.com  →  AWS App Runner (FastAPI container)
                                                        ├── RDS Postgres (data)
                                                        ├── SES (OTP email)
                                                        ├── Bedrock (Claude recognition)
                                                        └── S3 (consented capture images)
```

App Runner is chosen because it terminates HTTPS, provisions the custom-domain
cert automatically, autoscales, and needs no server management.

---

## 0. One-time prep
- Install/login AWS CLI (`aws sts get-caller-identity` should show `user/pete`).
- Have Docker Desktop running locally.

## 1. RDS Postgres
1. RDS console → Create database → **PostgreSQL**, template **Free tier** (or db.t4g.micro), single-AZ for now.
2. Set master user/password; DB name `weightprogram`.
3. **Public access: No** (App Runner will reach it via a VPC connector) — or **Yes** temporarily to simplify the first deploy, locked to your IP. Public+restricted is the easy path for a beta.
4. After creation, note the endpoint. Your connection string:
   ```
   DATABASE_URL=postgresql+asyncpg://<user>:<pass>@<endpoint>:5432/weightprogram
   ```

## 2. S3 bucket (capture images)
```
aws s3api create-bucket --bucket weightprogram-captures --region us-east-1
aws s3api put-public-access-block --bucket weightprogram-captures \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

## 3. Build & push the image to ECR
```
aws ecr create-repository --repository-name weightprogram-api --region us-east-1
aws ecr get-login-password --region us-east-1 | docker login --username AWS \
  --password-stdin 453371324700.dkr.ecr.us-east-1.amazonaws.com

cd backend
docker build -t weightprogram-api .
docker tag weightprogram-api:latest 453371324700.dkr.ecr.us-east-1.amazonaws.com/weightprogram-api:latest
docker push 453371324700.dkr.ecr.us-east-1.amazonaws.com/weightprogram-api:latest
```
(If you're on an Apple-Silicon Mac, add `--platform linux/amd64` to `docker build`.)

## 4. IAM role for the App Runner *instance*
The container needs to call SES, Bedrock, and S3. Create an instance role
(trust principal `tasks.apprunner.amazonaws.com`) with this policy:
```json
{ "Version": "2012-10-17", "Statement": [
  { "Sid": "Email",  "Effect": "Allow", "Action": ["ses:SendEmail","ses:SendRawEmail"], "Resource": "*" },
  { "Sid": "Vision", "Effect": "Allow", "Action": ["bedrock:InvokeModel"], "Resource": "*" },
  { "Sid": "Images", "Effect": "Allow", "Action": ["s3:PutObject","s3:DeleteObject"], "Resource": "arn:aws:s3:::weightprogram-captures/*" }
]}
```

## 5. App Runner service
1. App Runner console → Create service → Source: **Container registry → Amazon ECR**, pick the image you pushed. Deployment trigger: Manual (or automatic on push).
2. Service settings: port **8080**.
3. **Instance role**: the role from step 4.
4. Environment variables:
   ```
   ENVIRONMENT=production
   DATABASE_URL=postgresql+asyncpg://<user>:<pass>@<rds-endpoint>:5432/weightprogram
   JWT_SECRET=<openssl rand -hex 32>
   ACCESS_TOKEN_TTL_MINUTES=15
   REFRESH_TOKEN_TTL_DAYS=45
   AWS_REGION=us-east-1
   SES_FROM_EMAIL=no-reply@glpsteel.com
   EMAIL_DEV_MODE=false
   IMAGE_STORAGE_BACKEND=s3
   S3_BUCKET=weightprogram-captures
   VISION_PROVIDER=bedrock
   BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-6
   ```
5. If RDS is **not** public, add a **VPC connector** so App Runner can reach the DB subnet; ensure the RDS security group allows inbound 5432 from the connector's SG. (If RDS is public+IP-restricted, skip the connector but App Runner egress IPs vary — VPC connector is the durable answer.)
6. Deploy. App Runner gives you a default URL like `https://xxxx.us-east-1.awsapprunner.com` — test `/<that>/health` first.

## 6. Custom domain api.glpsteel.com
1. App Runner service → **Custom domains** → Add domain → `api.glpsteel.com`.
2. App Runner shows a set of **CNAME records** (domain validation + the target). Because the zone is in **Route 53**, add them there: Route 53 → hosted zone `glpsteel.com` → create the CNAME records exactly as shown.
3. Wait for validation (minutes to ~an hour). App Runner provisions the TLS cert automatically. `https://api.glpsteel.com/health` should then return ok.

## 7. SES for real OTP email
1. SES console → Verified identities → verify the **domain** `glpsteel.com`. SES gives DKIM CNAME records → add them in Route 53 (one click if SES offers Route 53 auto-publish).
2. While in the SES sandbox you can only send to verified recipients — verify your testers' emails, **or** request **production access** (Account dashboard → Request production access) so any tester gets codes. Do this early; approval can take ~24h.
3. `SES_FROM_EMAIL=no-reply@glpsteel.com` (covered by the verified domain).

## 8. Point the app at production
In `mobile/src/config.ts`:
```ts
export const API_BASE_URL = "https://api.glpsteel.com";
```
Commit, then build with EAS (see README/TestFlight steps).

## 9. Smoke test before building the app
```
curl https://api.glpsteel.com/health
# request a code (real email now), then verify, then /me
```

---

## Notes / beta caveats
- Tables auto-create on container start (`init_models`). Fine for the beta; move to **Alembic migrations** before you have real users you can't reset.
- App Runner runs 1+ instances; the in-memory singletons (email sender, recognizer) are per-instance and stateless, so scaling is safe.
- Rotate `JWT_SECRET` only when you intend to invalidate all sessions.
- Cost watch: App Runner (min ~$5–25/mo depending on size), RDS micro, Bedrock per-call, SES per-email. Fine for a beta; set a Budgets alert.
