#!/usr/bin/env bash
# Deploy the GLP Steel marketing site (website/index.html) to S3 + CloudFront.
# Runs on your Mac using your AWS credentials. Auto-detects the CloudFront
# distribution for glpsteel.com so there's no ID to hard-code.
#
#   bash website/deploy.sh
#
set -euo pipefail

SITE="/Volumes/2T_Media/Documents/WeightProgram/WeightProgram/website/index.html"
BUCKET="s3://glpsteel-website/index.html"

command -v aws >/dev/null || { echo "aws CLI not found on PATH." >&2; exit 1; }
[ -f "$SITE" ] || { echo "Missing $SITE" >&2; exit 1; }

echo "→ Uploading index.html to $BUCKET"
aws s3 cp "$SITE" "$BUCKET" \
  --content-type "text/html; charset=utf-8" \
  --cache-control "max-age=300"

echo "→ Locating CloudFront distribution for glpsteel.com"
DIST_ID=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?contains(Aliases.Items, 'glpsteel.com')].Id | [0]" \
  --output text)

if [ -z "$DIST_ID" ] || [ "$DIST_ID" = "None" ]; then
  echo "Could not auto-detect the distribution ID." >&2
  echo "Find it in the CloudFront console (starts with E) and run:" >&2
  echo "  aws cloudfront create-invalidation --distribution-id <ID> --paths '/*'" >&2
  exit 1
fi

echo "→ Invalidating CloudFront cache ($DIST_ID)"
aws cloudfront create-invalidation \
  --distribution-id "$DIST_ID" \
  --paths "/*" \
  --query "Invalidation.{Id:Id,Status:Status}" \
  --output table

echo "✓ Deployed. Live in ~1–2 min at https://glpsteel.com (hard-refresh to skip your browser cache)."
