# MEMORY.md

## Project Snapshot

- Project: `kali-publish`
- Created: 2026-09-14
- Goal: Extract the publishing backend from `/Users/yuerocky/Desktop/social-auto-upload-baijiahao` into a standalone GitHub project.

## Reusable Notes

- `~/.codex/templates/` was unavailable during bootstrap, so the required project files were created from the active workspace rules.
- The desktop source checkout is an input only; the extracted repository is created under this workspace.
- Credentials, local databases, generated media, logs, cookies, and session data must not be committed.
- The extraction boundary is the root publishing API and its automation adapters; `小程序后端/` and Notion, digital-human, material, payment, user, and credit features are out of scope.
- HTTP publishing keeps the original platform IDs: 1 小红书, 2 视频号, 3 抖音, 4 快手, 5 TikTok, 6 YouTube. API login is available for IDs 1–4; IDs 5–6 require a compatible pre-created browser state.
- Runtime configuration is environment-based through `conf.py`; the service listens on `127.0.0.1:5409` by default and must not be exposed directly to the public internet because it has no user authentication.
- Fresh-environment verification on Python 3.14 passed all six API and dispatch tests without invoking a real browser login or publish action.
- Canonical GitHub repository: `https://github.com/pabatiba89-sys/kali-publish`; visibility is public.
- The copied automation adapters derive from `dreammis/social-auto-upload`, whose MIT notice must remain in `LICENSE`; project-specific extraction and API code is released under the same license.
