---
name: xlsx
description: >
  Read and write Excel (.xlsx) workbooks — export a report, a cleaned dataset, or a
  digest table as a spreadsheet, or ingest an .xlsx the user uploads. Use when the
  user mentions Excel, spreadsheets, .xlsx, or asks to "export to a workbook".
  STUB in this demo — install the official Anthropic skill to activate (see below).
---

# xlsx (official skill — STUB)

This is a placeholder for Anthropic's official `xlsx` skill. It is **not installed**
in this environment because the sandbox network only permits the project repo
(cloning `anthropics/skills` returns 403 here).

## To install for real
```bash
npx openskills install anthropics/skills           # installs into ./.claude/skills
# or pin just this one from the upstream repo's document-skills/xlsx
```

## Intended role in this demo
A "next-step" output path: once a story or cleaned dataset exists, offer to export it
to `.xlsx` for Maya to share. Until installed, fall back to CSV via:
```bash
python tools/sql_tool.py --json "SELECT ..."   # then write CSV
```
