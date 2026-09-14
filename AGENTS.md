# AGENTS.md

## Project

- Name: kali-publish
- Last updated: 2026-09-14
- Purpose: Extract and publish a standalone backend project from `social-auto-upload-baijiahao`.
- Stack: Python 3.10+, Flask, Playwright/Patchright, SQLite.

## Working Rules

- Default communication language is Chinese; keep code, commands, variable names, and file paths in English.
- Read both `AGENTS.md` and `MEMORY.md` before project work.
- Store reusable project learnings in `MEMORY.md`; never store credential values.
- Treat source configuration, databases, uploads, logs, and session files as sensitive unless proven otherwise.
- Keep the desktop source checkout unchanged; build the standalone repository in this workspace.
- Before publishing, verify dependency completeness, secret exclusion, startup instructions, tests, and Git status.
