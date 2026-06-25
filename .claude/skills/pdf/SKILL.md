---
name: pdf
description: >
  Read, extract, and generate PDF documents — turn a story/report into a shareable
  PDF, or pull text/tables out of a PDF the user uploads (the seed of a future
  RAG line). Use when the user mentions PDF, "export the report as a PDF", or wants
  to query a document. STUB in this demo — install the official skill to activate.
---

# pdf (official skill — STUB)

Placeholder for Anthropic's official `pdf` skill. **Not installed** here (network is
restricted to the project repo). This is the P2 "PDF / RAG" line, intentionally
deferred to a next step per the project scope.

## To install for real
```bash
npx openskills install anthropics/skills
```

## Intended role (next step)
- **Out:** render `reports/story_C.md` / `story_B.md` to a polished PDF for sharing.
- **In (RAG seed):** ingest an uploaded PDF (e.g. a deploy postmortem) so the agent
  can cross-reference the alert finding against written context.

Deferred on purpose — listed so the orchestration layer has a stable interface to
call once the skill is installed.
