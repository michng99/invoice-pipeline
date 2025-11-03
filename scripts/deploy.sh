#!/usr/bin/env bash
set -euo pipefail

# cấu hình
PROJECT_ID="$(gcloud config get-value project)"
REGION="asia-southeast1"
SERVICE="invoice-pipeline"

cd "$HOME/invoice-pipeline"

# (A) Deploy trực tiếp từ source (không cần Dockerfile)
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --port 8080 \
  --project "$PROJECT_ID"

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
echo "✅ Deployed: $URL"
echo "$URL" > fe/.backend_url

echo "👉  Dùng FE script để chạy:  scripts/fe.sh $URL"
