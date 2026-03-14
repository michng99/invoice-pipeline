# PROMPTS.md — AI-assisted Development Playbook (Gemini CLI)

This repo is an end-to-end document processing pipeline:
**Batch XML invoices → parse/normalize → export structured XLSX** (FastAPI + Streamlit).

I use **Gemini CLI** as a coding assistant to scaffold/refactor code faster, then I manually review and harden output using a validation checklist and real sample files.

---

## How to use these prompts
- Always provide **sample XML snippets** (or sanitized fields) and the **expected XLSX column schema**.
- Ask the agent to propose **edge cases** and **failure modes**.
- After applying generated code, validate via:
  - batch run with mixed good/bad XML files
  - verifying required columns exist
  - checking stable column mapping (deterministic output)
  - confirming failed files are skipped and reported (not crash the app)

---

## Prompt Library

### A) Parsing & XML Edge Cases
**Prompt A1 — Robust XML parsing**
> You are working on a Python XML invoice pipeline. Given these sample XML structures (paste samples), propose a robust parsing approach, including how to handle missing nodes, namespaces, and unexpected nesting. Output should be safe and deterministic.

**Prompt A2 — Defensive extraction**
> Write a helper that extracts values from nested dict-like XML structures (from xmltodict) safely. Must avoid KeyError and return defaults for missing fields.

**Prompt A3 — Identify failure patterns**
> From these XML samples, list common failure patterns (malformed XML, missing tags, inconsistent types). For each pattern, propose how to handle it while keeping the batch pipeline running.

---

### B) Schema Mapping / Normalization
**Prompt B1 — Normalize to schema**
> I need to normalize invoice data into a fixed schema for XLSX columns: (list columns). Propose a mapping strategy and how to handle optional fields. Output must keep column names stable.

**Prompt B2 — Deterministic column mapping**
> Ensure output XLSX columns are deterministic and consistent across runs. Suggest rules for ordering, default values, and type normalization.

**Prompt B3 — Rows generation**
> Given a parsed invoice dict (paste example), generate a list of row dicts aligned to the schema. Include a plan for invoices with multiple line items.

---

### C) XLSX Export
**Prompt C1 — XLSX writer**
> Implement an XLSX exporter that writes rows to a sheet with a stable column order. Must handle large batches reasonably and avoid corrupt files.

**Prompt C2 — Formatting (optional)**
> Suggest minimal formatting improvements for readability (freeze header row, column widths) without overcomplicating the code.

---

### D) Error Handling & Reliability
**Prompt D1 — Skip-and-continue design**
> Design error handling for batch processing: if one file fails parsing/mapping, skip it and continue processing other files. Provide a structured error summary (file name + reason).

**Prompt D2 — Fail-safe system wrapper**
> Propose a top-level error wrapper that catches critical failures (system-level errors) and returns a generic message to users, while keeping details only in server logs.

**Prompt D3 — User-safe error messaging**
> In a Streamlit UI, how can we show a user-friendly error summary without leaking stack traces? Provide recommended patterns.

---

### E) Refactoring & Code Quality
**Prompt E1 — Refactor core functions**
> Refactor these functions for readability and maintainability: _parse_invoice, _rows_from_invoice (paste code). Keep behavior identical and preserve skip-and-continue semantics.

**Prompt E2 — Improve readability**
> Suggest improvements for naming, separation of concerns, and function boundaries. Avoid introducing heavy abstractions.

**Prompt E3 — Add minimal logging**
> Propose a lightweight server-side logging approach for each pipeline stage (ingest → parse → normalize → export). Keep logs useful for debugging without leaking sensitive data.

---

## Validation Checklist (manual)
- [ ] Batch upload mixed XML files: valid + malformed + missing fields
- [ ] Confirm app **does not crash** when a file fails
- [ ] Failed files are **skipped** and included in an error summary
- [ ] Output XLSX has **stable columns** and deterministic mapping
- [ ] Streamlit UI does **not show stack traces** (server-only details)
- [ ] Review AI-generated code manually before merging
