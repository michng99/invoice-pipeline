# AGENTS.md — “Agent Roles” Orchestration (Human-in-the-loop)

This project is developed with an **AI-assisted, agent-like workflow**, coordinated manually (human-in-the-loop).
I use **Gemini CLI** as the primary assistant to speed up coding, then I validate and harden changes before shipping.

This is NOT an autonomous multi-agent runtime system.
It is a **development workflow** that assigns different “roles” to the assistant.

---

## Agent Roles

### 1) Builder Agent
Goal: scaffold features quickly.
- Generate initial implementation for parsing/mapping/export tasks
- Propose minimal architecture and code structure changes
- Provide code patches and explain trade-offs

### 2) Reviewer/Hardening Agent
Goal: improve reliability and safety.
- Identify edge cases and failure modes
- Suggest validation rules and safer defaults
- Review for deterministic outputs, safe error handling, and minimal leakage

### 3) Tester/Validator Agent (lightweight)
Goal: reduce regression risk with practical checks.
- Suggest test cases (even if manual)
- Create small validation scripts/checklists
- Ensure skip-and-continue behavior works as intended

### 4) Doc Agent
Goal: keep docs usable.
- Update README usage instructions
- Document limitations and common errors
- Provide example input/output format notes

---

## Orchestration Flow (human-in-the-loop)
1) **Define requirements**
   - what users upload, expected output schema, sample XML edge cases
2) **Builder Agent**
   - generate scaffold / implement core changes
3) **Reviewer/Hardening Agent**
   - add validation + strengthen error handling + ensure deterministic mapping
4) **Tester/Validator Agent**
   - propose checks (batch mixed files) + verify skip-and-continue
5) **Doc Agent**
   - update README + add notes on known limitations

---

## Reliability Principles used in this repo
- **Skip-and-continue (file-level):**
  - if 1 file fails parsing/mapping, it is skipped and processing continues for remaining files
- **Fail-safe (system-level):**
  - a top-level wrapper catches critical failures and surfaces generic user messages
- **Server-side logging:**
  - detailed errors/tracebacks are kept server-side for debugging
  - Streamlit UI hides error details to avoid leaking internals

---

## Artifacts
- Prompt patterns and hardening checklist: `PROMPTS.md`
- Workflow role definitions: `AGENTS.md`
- Notes and run instructions: `README.md`
