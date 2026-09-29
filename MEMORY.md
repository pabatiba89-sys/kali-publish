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
- HTTP publishing keeps IDs 1 小红书, 2 视频号, 3 抖音, 4 快手, 5 TikTok, 6 YouTube, and adds 7 X, 8 Instagram, 9 Facebook. Browser login is available for IDs 1–6; IDs 7–9 use imported official-API credentials.
- Runtime configuration is environment-based through `conf.py`; the service listens on `127.0.0.1:5409` by default and must not be exposed directly to the public internet because it has no user authentication.
- Fresh-environment verification on Python 3.14 passed 21 API, dispatch, credential-security, and adapter tests; the rebuilt Apple Silicon bundle also passed browser and `/health` smoke checks. Real platform posts still require user-owned accounts and credentials.
- Canonical GitHub repository: `https://github.com/pabatiba89-sys/kali-publish`; visibility is public.
- The copied automation adapters derive from `dreammis/social-auto-upload`, whose MIT notice must remain in `LICENSE`; project-specific extraction and API code is released under the same license.
- Executable releases use a PyInstaller one-directory bundle and call the user's installed Google Chrome instead of redistributing a Playwright browser. `LOCAL_CHROME_PATH` remains the explicit override.
- Release `v1.0.0` targets Apple Silicon with `macos-15` and Windows x64 with `windows-2025`; both archives are unsigned and include a SHA-256 checksum.
- The local Apple Silicon package was verified as an arm64 executable: its packaged Playwright driver launched system Chrome and its `/health` endpoint responded successfully.
- GitHub Actions run `34804380222` passed both platform builds and published the verified public release at `https://github.com/pabatiba89-sys/kali-publish/releases/tag/v1.0.0`.
- Public-facing project copy should focus only on supported publishing capabilities and how to use them; omit extraction history and unrelated excluded-business descriptions.
- Overseas platform IDs are 5 TikTok, 6 YouTube, 7 X, 8 Instagram, and 9 Facebook. TikTok/YouTube use local browser sessions; X/Instagram/Facebook use official API credentials imported through `/api/accounts/import` and stored as mode-0600 files under `cookiesFile/`.
- Native scheduling is exposed only where implemented: TikTok and Facebook support it; YouTube, X, and Instagram currently reject scheduled requests instead of silently publishing immediately.
