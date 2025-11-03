#!/usr/bin/env bash
set -euo pipefail
cd ~/invoice-pipeline

[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate

python - <<'PY' || python -m pip install -q --upgrade pip wheel && python -m pip install -q "streamlit==1.39.0" "requests"
import importlib.util, sys
mods = ["streamlit","requests"]
missing = [m for m in mods if importlib.util.find_spec(m) is None]
sys.exit(1 if missing else 0)
PY

pkill -f "streamlit run" 2>/dev/null || true
cd fe
python -m streamlit run streamlit_app.py \
  --server.address 0.0.0.0 \
  --server.port 8080 \
  --server.enableCORS false \
  --server.enableXsrfProtection false \
  --browser.gatherUsageStats false
