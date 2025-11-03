#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID=$(gcloud config get-value project)
REGION=asia-southeast1
BACKEND_URL="${BACKEND_URL:-https://invoice-pipeline-160913806.asia-southeast1.run.app}"

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

gcloud artifacts repositories create invoice-fe \
  --repository-format=docker \
  --location=$REGION \
  --description="FE Streamlit images" || true

cd "$(dirname "$0")"
TAG=$(date +%Y%m%d-%H%M%S)
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/invoice-fe/streamlit-fe:$TAG"

gcloud builds submit --tag "$IMAGE"

gcloud run deploy streamlit-fe \
  --image "$IMAGE" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --set-env-vars BACKEND_URL="$BACKEND_URL" \
  --min-instances=0 --max-instances=3 --memory=512Mi --cpu=1
