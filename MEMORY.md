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
- HTTP publishing keeps IDs 1 小红书, 2 视频号, 3 抖音, 4 快手, 5 TikTok, 6 YouTube, 7 X, 8 Instagram, 9 Facebook, and adds 10 支付宝生活号. All ten platforms use local browser login; official-API credential import is retired.
- Runtime configuration is environment-based through `conf.py`; the service listens on `127.0.0.1:5409` by default and must not be exposed directly to the public internet because it has no user authentication.
- Current source verification on Python 3.14 passes 37 API, dispatch, browser-runtime, login, and adapter tests plus the browser self-test; the prior Apple Silicon bundle also passed browser and `/health` smoke checks. Real platform posts still require user-owned accounts and interactive login.
- Canonical GitHub repository: `https://github.com/pabatiba89-sys/kali-publish`; visibility is public.
- The copied automation adapters derive from `dreammis/social-auto-upload`, whose MIT notice must remain in `LICENSE`; project-specific extraction and API code is released under the same license.
- Executable releases use a PyInstaller one-directory bundle and call the user's installed Google Chrome instead of redistributing a Playwright browser. `LOCAL_CHROME_PATH` remains the explicit override.
- Release `v1.0.0` targets Apple Silicon with `macos-15` and Windows x64 with `windows-2025`; both archives are unsigned and include a SHA-256 checksum.
- The local Apple Silicon package was verified as an arm64 executable: its packaged Playwright driver launched system Chrome and its `/health` endpoint responded successfully.
- GitHub Actions run `34804380222` passed both platform builds and published the verified public release at `https://github.com/pabatiba89-sys/kali-publish/releases/tag/v1.0.0`.
- Public-facing project copy should focus only on supported publishing capabilities and how to use them; omit extraction history and unrelated excluded-business descriptions.
- Overseas platform IDs are 5 TikTok, 6 YouTube, 7 X, 8 Instagram, and 9 Facebook; all use saved local browser sessions. Browser login states are stored under `cookiesFile/` and API credential import is no longer exposed.
- Native scheduling is exposed only where implemented: TikTok supports it; YouTube, X, Instagram, Facebook, and Alipay Life Account reject scheduled requests instead of silently publishing immediately.
- Google rejects sign-in inside Playwright/Patchright-controlled Chrome even when the installed Chrome channel is used. YouTube first-time sign-in must run in a regular Chrome process with a dedicated `cookiesFile/youtube-*` profile; automation may reuse that profile only after sign-in is complete.
- The same Google restriction applies when X, Instagram, or Facebook delegates sign-in to Google. Their first-time login must use a regular Chrome process with dedicated `cookiesFile/web-*` profiles; do not regress these flows to Playwright-controlled sign-in.
- The active legacy publishing database is `/Users/yuerocky/Desktop/social-auto-upload-baijiahao/db/database.db`; the similarly named database at the legacy project root is empty. The standalone project uses its own migrated copy, copied account states, and hard-linked existing legacy videos so the source checkout remains unchanged without duplicating 25 GB.
- Tencent Channels publishing follows the legacy business rule: append `#喀理系统` and `@岳同学AI`, then select the second content-mark option when the new `mark-tag-select` UI is available.
- The 2026-09 browser-flow refresh selectively follows `dreammis/social-auto-upload` commit `0012d2c355f88f683cc38dde2a2db209e14091bc`: migrate its newer TikTok Studio and Alipay Life Account behavior, keep the local YouTube ordinary-Chrome login fix, the TikTok iframe fix, and correct five-minute rounding.
- `leaperone/MultiPost-Extension` commit `6269ab4ada1cf661a3624b2b9f496bb032a391d5` was reviewed as a second browser-publishing reference. Its useful cross-platform content-field conventions were adopted, but its weaker upload-success checks and browser-extension-only injection architecture were not copied.
