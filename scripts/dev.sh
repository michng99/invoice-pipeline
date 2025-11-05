#!/usr/bin/env bash
set -euo pipefail

ROOT="$HOME/invoice-pipeline"
cd "$ROOT"

# 1) Venv + install deps
if [[ ! -d ".venv" ]]; then
  echo "▶️  Creating virtual environment '.venv'..."
  python3 -m venv .venv
fi
source .venv/bin/activate || { echo "❌ Failed to activate virtualenv."; exit 1; }
python -m pip -q install --upgrade pip
python -m pip -q install -r requirements.txt \
  fastapi "uvicorn[standard]" pandas xmltodict XlsxWriter openpyxl python-multipart \
  streamlit requests

# 2) Kill phiên cũ (nếu có)
pkill -f "uvicorn app.main:app" >/dev/null 2>&1 || true
pkill -f "streamlit run" >/dev/null 2>&1 || true

# 3) Chạy BACKEND (FastAPI) trên 8000
echo "▶️  Start FastAPI on 0.0.0.0:8000 ..."
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &

# 4) Chờ /health OK
echo "⏳  Wait backend /health ..."
export no_proxy="127.0.0.1,localhost"
for i in {1..40}; do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null; then
    echo "✅ Backend OK"
    break
  fi
  sleep 0.3
  [[ $i -eq 40 ]] && { echo "❌ Backend không lên. Log: /tmp/uvicorn.log"; tail -n 200 /tmp/uvicorn.log || true; exit 1; }
done

# 5) Chạy FRONTEND (Streamlit) trên 8080, trỏ backend local
export BACKEND_URL="http://127.0.0.1:8000"
export STREAMLIT_SERVER_HEADLESS=true
export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

echo "▶️  Start Streamlit on 0.0.0.0:8080 (BACKEND_URL=$BACKEND_URL) ..."
python -m streamlit run fe/streamlit_app.py \
  --server.address 0.0.0.0 \
  --server.port 8080 \
  --server.enableCORS false \
  --server.enableXsrfProtection false
