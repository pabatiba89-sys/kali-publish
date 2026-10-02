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
- Current source verification on Python 3.14 includes API, dispatch, browser-runtime, login, adapter, and real-Chrome DOM regression tests. Real platform posts still require user-owned accounts and interactive login; reaching the final button is not proof of publication.
- Canonical GitHub repository: `https://github.com/pabatiba89-sys/kali-publish`; visibility is public.
- The copied automation adapters derive from `dreammis/social-auto-upload`, whose MIT notice must remain in `LICENSE`; project-specific extraction and API code is released under the same license.
- Executable releases use a PyInstaller one-directory bundle and call the user's installed Google Chrome instead of redistributing a Playwright browser. `LOCAL_CHROME_PATH` remains the explicit override.
- Release `v1.0.0` targets Apple Silicon with `macos-15` and Windows x64 with `windows-2025`; both archives are unsigned and include a SHA-256 checksum.
- The local Apple Silicon package was verified as an arm64 executable: its packaged Playwright driver launched system Chrome and its `/health` endpoint responded successfully.
- GitHub Actions run `34804380222` passed both platform builds and published the verified public release at `https://github.com/pabatiba89-sys/kali-publish/releases/tag/v1.0.0`.
- Public-facing project copy should focus only on supported publishing capabilities and how to use them; omit extraction history and unrelated excluded-business descriptions.
- Overseas platform IDs are 5 TikTok, 6 YouTube, 7 X, 8 Instagram, and 9 Facebook; all use saved local browser sessions. Browser login states are stored under `cookiesFile/` and API credential import is no longer exposed.
- Native scheduling is exposed only where implemented: TikTok supports it. YouTube, X, Instagram, Facebook, and Alipay Life Account silently fall back to immediate publishing when a scheduled request is received.
- Google rejects sign-in inside Playwright/Patchright-controlled Chrome even when the installed Chrome channel is used. TikTok, YouTube, X, Instagram, and Facebook first-time sign-in must run in a regular Chrome process with a dedicated local profile.
- On macOS, regular Chrome encrypts profile cookies with the system Keychain while Playwright/Patchright launches Chrome with a mock keychain; opening the raw login profile for publishing makes the session unreadable and may delete its cookies. At login completion, connect to ordinary Chrome over a fixed non-zero loopback debugging port, export `storage-state.json`, and make publishing consume only that export. A fixed non-zero port keeps `navigator.webdriver` false; do not use `--remote-debugging-port=0` for login.
- YouTube, X, Instagram, and Facebook ordinary-Chrome login completion must be detected from each platform's required Cookie names, never from Chrome History URLs. Read only Cookie names for this check; never read or expose Cookie values.
- `/getValidAccounts` performs live Cookie validation only for Tencent Channels (platform type 2). Other platforms retain their stored status so refreshing account management does not open browser validation sessions.
- The standalone backend must keep the legacy-compatible `POST /uploadFromUrl` contract because the web publishing flow downloads finished CDN videos through port 5409 before calling `/postVideo`. Its CORS preflight must return 2xx; a missing route appears in browsers as a CORS failure.
- By explicit product decision, only the local `/uploadFromUrl` downloader ignores HTTPS certificate validation errors. Keep this exception narrowly scoped; private/local address blocking, redirect validation, and download size limits remain required.
- The active legacy publishing database is `/Users/yuerocky/Desktop/social-auto-upload-baijiahao/db/database.db`; the similarly named database at the legacy project root is empty. The standalone project uses its own migrated copy, copied account states, and hard-linked existing legacy videos so the source checkout remains unchanged without duplicating 25 GB.
- Tencent Channels publishing follows the legacy business rule: append `#喀理系统` and `@岳同学AI`, then select the second content-mark option when the new `mark-tag-select` UI is available.
- The 2026-09 browser-flow refresh selectively follows `dreammis/social-auto-upload` commit `0012d2c355f88f683cc38dde2a2db209e14091bc`: migrate its newer TikTok Studio and Alipay Life Account behavior, keep the local YouTube ordinary-Chrome login fix, the TikTok iframe fix, and correct five-minute rounding.
- `leaperone/MultiPost-Extension` commit `6269ab4ada1cf661a3624b2b9f496bb032a391d5` was reviewed as a second browser-publishing reference. Its useful cross-platform content-field conventions were adopted, but its weaker upload-success checks and browser-extension-only injection architecture were not copied.
- Instagram web `/create/select/` can resolve to the unrelated @create profile. Open the composer through the homepage navigation, select only a video-accepting input, dismiss the first-video Reels notice, and support localized Continue controls and contenteditable captions.
- TikTok's `?lang=en` does not guarantee English UI. Wait for the video input in the main page or an iframe after DOMContentLoaded instead of full load or an English button label. Chinese Studio uses 发布 and can show a first-use 知道了 overlay. Submit once, then wait for confirmation to avoid duplicate submissions.
- YouTube publishing must remain public by default; do not substitute private verification for a requested public publish. Final-submit success requires matching the uploaded video ID and requested visibility in the Studio content table, including Shorts links. Close only an identified completion dialog; never blindly accept arbitrary warnings or infer success from clicking the first submit button.
- Live YouTube Studio verification must use the same headed browser configuration and initialization as the uploader. On 2026-10-02 a headless diagnostic received the unsupported-browser interstitial; the headed check successfully verified the existing public video without uploading again.
- Xiaohongshu's current `xhs-publish-btn` has a closed shadow root: neither `button:has-text("发布")` nor page text locators can see its internal submit button. Read only this component through Chrome CDP, wait for its actual button to become enabled, and perform one normal pointer click at its measured bounds; never synthesize a submit or bypass its disabled state. Confirm the success URL and use bounded waits instead of busy-looping/repeated submissions. A live upload reached the success page with this approach on 2026-10-02.
- Instagram can remain on 正在分享 after submission; the user's minimum processing/result wait is 15 minutes, including file transfer and edit transitions, not only button discovery. A short default click timeout must not override this longer processing allowance.
- X can retain duplicate home-timeline controls behind its composer. Scope Post to the visible composer and skip hidden/disabled matches; avoid using a globally indexed editor locator as a relative `has` filter. Facebook Reels must recognize 下一页/下一頁 and 分享 as well as 下一步/发布; use a taller publishing viewport for clipped footer controls. These changes have local browser regression coverage, not yet live posting verification.
- User screenshots identify TikTok's 继续发布?/立即发布 and YouTube's 我们仍在检查你的内容/仍然发布 dialogs as unfinished-check warnings, not success dialogs. Automatically accepting these requires the user's choice about publishing before checks complete; never treat their presence as publication success.
