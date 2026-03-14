# Invoice Pipeline — Batch XML → JSON → XLSX (FastAPI + Streamlit)

A practical document-processing pipeline to **batch convert multiple e-invoice XML files** into **structured Excel (XLSX)** for reporting.
Built with **FastAPI (backend APIs)** + **Streamlit (web UI)**. Initially deployed on **GCP (Cloud Run)**, later migrated UI hosting to **Streamlit Community Cloud** for cost efficiency.

> Repo: https://github.com/michng99/invoice-pipeline  
> Demo: https://xulydulieu.streamlit.app *(if demo is gated, add a short video demo link here)*

---

## What it does
**Workflow:** Upload multiple XML files → Parse/Validate → Transform into normalized rows/columns → Export **XLSX**.

This project focuses on:
- fast iteration for real-world workflows
- robust handling of messy/inconsistent XML inputs
- batch UX (process many files in one run)

---

## Tech Stack
- **Backend:** Python, FastAPI, Pydantic
- **Frontend:** Streamlit
- **Data processing:** XML parsing, transformation pipeline, pandas
- **Export:** XLSX (openpyxl / xlsxwriter)
- **Cloud/DevOps:** Docker, GCP Cloud Run, Cloud Build (CI/CD)
- **AI-assisted development:** Gemini CLI (primary), Cursor/CodeX (limited due to cost)

---

## Architecture (high level)
- **Streamlit UI**: handles user upload + triggers processing + returns download
- **FastAPI backend**:
  - parse invoice XML → dict/JSON
  - normalize fields into schema-aligned rows
  - export Excel file (XLSX)

---

## Quality & Reliability
- **Skip-and-continue (file-level):** if a user uploads 10 XML files and 1 file is malformed or fails mapping, the app **skips that file** and continues processing the remaining files (batch-friendly UX).
- **Fail-safe (system-level):** critical exceptions are caught at a higher level to prevent crashes and show a **generic message** to users.
- **Server-side logging:** detailed error traces are kept server-side (terminal/Streamlit logs) for debugging.
- **Safe UI errors:** Streamlit is configured to hide detailed error information (`showErrorDetails = false`) to reduce accidental leakage of internal details.
- **Deterministic structure:** stable column/schema structure for repeatable XLSX exports across runs *(keep this only if your schema mapping is stable in practice).*

---

## Run locally

### 1) Requirements
- Python 3.10+ recommended
- (Optional) `pipx`/`venv`

### 2) Setup environment
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3) Start Backend (FastAPI)
```bash
uvicorn app.main:app --reload --port 8000
```

Backend should be available at:
- API: http://localhost:8000
- Docs: http://localhost:8000/docs

### 4) Start Frontend (Streamlit)
```bash
streamlit run fe/streamlit_app.py
```

---

## Usage
1) Open Streamlit UI
2) Upload multiple XML files
3) Click **Process**
4) Download the generated Excel (XLSX)

**Expected behavior:**
- Invalid XML files are skipped and logged server-side
- Valid files still produce an output XLSX

---

## Deployment Notes

### Option A — GCP Cloud Run (backend)
This repo includes a `cloudbuild.yaml` for building/pushing images and deploying to Cloud Run (backend + optionally frontend).
Typical flow:
- Build Docker image
- Push to Artifact Registry
- Deploy to Cloud Run

> If you use Cloud Build triggers, ensure env variables and permissions are set correctly.

### Option B — Streamlit Community Cloud (UI)
After GCP credits ended, the UI was moved to Streamlit hosting for cost efficiency.
Backend can still be hosted elsewhere (Cloud Run, Render, Railway, etc.) and the Streamlit UI can call it via API.

---

## AI-assisted Development Artifacts
To match an AI-first engineering workflow:
- `PROMPTS.md` — curated prompts and a validation checklist (Gemini CLI)
- `AGENTS.md` — “agent roles” orchestration (human-in-the-loop)

---

## Roadmap (optional)
- Better per-file error summary in UI (filename + reason)
- Additional schema templates / configurable column mapping
- Minimal tests for parser/normalizer (pytest)

---

## License
Choose a license if you want (MIT is common). Otherwise, remove this section.
