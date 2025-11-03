#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate 2>/dev/null || (python3 -m venv .venv && source .venv/bin/activate)
pip -q install --upgrade pip
[ -f requirements.txt ] && pip -q install -r requirements.txt || pip -q install fastapi "uvicorn[standard]" pandas xmltodict XlsxWriter openpyxl python-multipart
mkdir -p out
for f in input*.xml; do
  [ -f "$f" ] || continue
  o="out/$(basename "${f%.xml}")-$(date +%Y%m%d-%H%M%S).xlsx"
  echo "→ $f  →  $o"
  python offline_convert.py "$f" "$o"
  sleep 1
done
python - <<'PY'
import glob, pandas as pd
files = sorted(glob.glob("out/*.xlsx"))
assert files, "Không thấy file trong out/"
dfs=[]
for f in files:
    try:
        df=pd.read_excel(f); df["__NguonFile"]=f; dfs.append(df)
    except Exception as e:
        print("⚠️ Bỏ qua", f, e)
pd.concat(dfs, ignore_index=True).to_excel("Data-Master.xlsx", index=False)
print("✅ Đã tạo Data-Master.xlsx")
PY
cloudshell download Data-Master.xlsx
