#!/usr/bin/env bash
set -euo pipefail

ROOT="$HOME/invoice-pipeline"
cd "$ROOT"
source .venv/bin/activate 2>/dev/null || { python3 -m venv .venv; source .venv/bin/activate; }

python -m pip -q install --upgrade pip
python -m pip -q install streamlit requests

# Đọc URL từ đối số hoặc file
BACKEND_URL="${1:-}"
if [[ -z "${BACKEND_URL}" ]]; then
  [[ -f fe/.backend_url ]] && BACKEND_URL="$(cat fe/.backend_url)"
fi
if [[ -z "${BACKEND_URL}" ]]; then
  echo "❌ Chưa có BACKEND_URL. Dùng: scripts/fe.sh https://<cloud-run>.run.app"
  exit 1
fi

echo "$BACKEND_URL" > fe/.backend_url

pkill -f "streamlit run" >/dev/null 2>&1 || true
export BACKEND_URL
export STREAMLIT_SERVER_HEADLESS=true
export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

echo "▶️  Streamlit on 0.0.0.0:8080 (BACKEND_URL=$BACKEND_URL)"
python -m streamlit run fe/streamlit_app.py \
  --server.address 0.0.0.0 \
  --server.port 8080 \
  --server.enableCORS false \
  --server.enableXsrfProtection false
