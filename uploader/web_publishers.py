from __future__ import annotations

import asyncio
import re
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

from playwright.async_api import Locator, Page, Playwright, TimeoutError as PlaywrightTimeoutError, async_playwright

from conf import BASE_DIR, LOCAL_CHROME_HEADLESS
from utils.base_social_media import set_init_script
from utils.browser_runtime import (
    chrome_profile_has_cookies,
    chrome_storage_state_path,
    chromium_launch_options,
    reserve_loopback_port,
    resolve_chrome_executable,
    save_chrome_storage_state,
)
from utils.log import facebook_logger, instagram_logger, x_logger
from utils.publish_lifecycle import close_owned_browser

PROCESSING_TIMEOUT_MS = 15 * 60 * 1000

WEB_PLATFORMS = {
    7: {
        "name": "X",
        "login_url": "https://x.com/i/flow/login",
        "home_url": "https://x.com/home",
        "cookies": {"auth_token"},
        "cookie_domains": ("x.com",),
        "logger": x_logger,
    },
    8: {
        "name": "Instagram",
        "login_url": "https://www.instagram.com/accounts/login/",
        "home_url": "https://www.instagram.com/",
        "cookies": {"sessionid"},
        "cookie_domains": ("instagram.com",),
        "logger": instagram_logger,
    },
    9: {
        "name": "Facebook",
        "login_url": "https://www.facebook.com/login/",
        "home_url": "https://www.facebook.com/",
        "cookies": {"c_user", "xs"},
        "cookie_domains": ("facebook.com",),
        "logger": facebook_logger,
    },
}


def _config(platform_type: int) -> dict:
    try:
        return WEB_PLATFORMS[int(platform_type)]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Unsupported browser platform type: {platform_type}") from exc


async def _has_login_cookies(context, required: set[str]) -> bool:
    names = {cookie.get("name") for cookie in await context.cookies()}
    return required.issubset(names)


def _authenticated_url_from_history(profile_dir: Path, patterns: tuple[str, ...]) -> str:
    """Read only the most recent authenticated URL from a dedicated Chrome profile."""
    for history_path in (profile_dir / "Default" / "History", profile_dir / "History"):
        if not history_path.is_file():
            continue
        try:
            uri = f"{history_path.resolve().as_uri()}?mode=ro"
            where = " OR ".join("url LIKE ?" for _ in patterns)
            with closing(sqlite3.connect(uri, uri=True, timeout=0.2)) as connection:
                row = connection.execute(
                    f"SELECT url FROM urls WHERE {where} "
                    "ORDER BY last_visit_time DESC LIMIT 1",
                    patterns,
                ).fetchone()
            if row:
                return str(row[0])
        except (OSError, sqlite3.Error):
            continue
    return ""


def _stop_chrome_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


async def browser_cookie_gen(platform_type: int, account_file) -> dict:
    """Use a regular Chrome profile so Google OAuth does not reject the login browser."""
    config = _config(platform_type)
    profile_dir = Path(account_file)
    profile_dir.mkdir(parents=True, exist_ok=True)
    try:
        profile_dir.chmod(0o700)
    except OSError:
        pass
    logger = config["logger"]
    chrome = resolve_chrome_executable()
    debug_port = reserve_loopback_port()
    process = subprocess.Popen(
        [
            str(chrome),
            f"--user-data-dir={profile_dir}",
            "--profile-directory=Default",
            f"--remote-debugging-port={debug_port}",
            "--remote-debugging-address=127.0.0.1",
            "--no-first-run",
            "--new-window",
            config["login_url"],
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    logger.info(f"请在弹出的普通 Chrome 窗口完成 {config['name']} 登录")
    current_url = ""
    try:
        for _ in range(600):
            if chrome_profile_has_cookies(
                profile_dir, config["cookie_domains"], config["cookies"]
            ):
                await asyncio.sleep(2)
                if await save_chrome_storage_state(
                    debug_port, chrome_storage_state_path(profile_dir)
                ):
                    current_url = config["home_url"]
                break
            if process.poll() is not None:
                if chrome_profile_has_cookies(
                    profile_dir, config["cookie_domains"], config["cookies"]
                ):
                    if await save_chrome_storage_state(
                        debug_port, chrome_storage_state_path(profile_dir)
                    ):
                        current_url = config["home_url"]
                break
            await asyncio.sleep(1)
    finally:
        _stop_chrome_process(process)
    success = bool(current_url)
    return {
        "success": success,
        "status": "logged_in" if success else "timeout",
        "message": "登录成功" if success else "登录未完成或已超时",
        "account_file": str(profile_dir),
        "current_url": current_url,
    }


async def _open_account_context(playwright: Playwright, account_file, headless: bool):
    account_path = Path(account_file)
    options = chromium_launch_options(headless=headless)
    if account_path.is_dir():
        storage_state = chrome_storage_state_path(account_path)
        if not storage_state.is_file():
            raise FileNotFoundError(f"Browser login state is missing: {storage_state}")
    else:
        storage_state = account_path
    browser = await playwright.chromium.launch(**options)
    context = await browser.new_context(storage_state=storage_state)
    return context, browser


async def _close_account_context(context, browser) -> None:
    await close_owned_browser(context, browser, x_logger)


async def _browser_cookie_auth(playwright: Playwright, platform_type: int, account_file) -> bool:
    config = _config(platform_type)
    account_path = Path(account_file)
    if not account_path.exists():
        return False
    context = None
    browser = None
    try:
        context, browser = await _open_account_context(
            playwright, account_path, headless=True
        )
        context = await set_init_script(context)
        page = await context.new_page()
        await page.goto(config["home_url"], wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_timeout(2000)
        return (
            "login" not in page.url.lower()
            and await _has_login_cookies(context, config["cookies"])
        )
    except Exception:
        return False
    finally:
        if context is not None:
            await _close_account_context(context, browser)


async def browser_cookie_auth(platform_type: int, account_file) -> bool:
    async with async_playwright() as playwright:
        return await _browser_cookie_auth(playwright, platform_type, account_file)


async def _first_visible(locators: list[Locator], timeout: int = 30000) -> Locator:
    deadline = asyncio.get_running_loop().time() + timeout / 1000
    while asyncio.get_running_loop().time() < deadline:
        for locator in locators:
            try:
                for candidate in await locator.all():
                    if await candidate.is_visible():
                        return candidate
            except Exception:
                continue
        await asyncio.sleep(0.25)
    raise TimeoutError("No matching visible element appeared")


async def _click_text(page: Page, labels: list[str], timeout: int = 30000) -> None:
    locators = []
    for label in labels:
        locators.extend(
            [
                page.get_by_role("button", name=label, exact=True),
                page.get_by_text(label, exact=True),
                page.locator(f'[aria-label="{label}"]'),
            ]
        )
    locator = await _first_visible(locators, timeout=timeout)
    await locator.click(timeout=timeout)


async def _wait_enabled(locator: Locator, timeout: int = 180000) -> Locator:
    deadline = asyncio.get_running_loop().time() + timeout / 1000
    while asyncio.get_running_loop().time() < deadline:
        try:
            for candidate in await locator.all():
                if await candidate.is_visible() and await candidate.is_enabled():
                    if await candidate.get_attribute("aria-disabled") != "true":
                        return candidate
        except Exception:
            pass
        await asyncio.sleep(1)
    raise TimeoutError("Publish button did not become enabled")


class BrowserVideoPublisher:
    platform_type: int
    platform_slug: str

    def __init__(
        self,
        title,
        file_path,
        tags,
        account_file,
        description="",
        headless=LOCAL_CHROME_HEADLESS,
    ):
        self.title = str(title or "")
        self.file_path = str(file_path)
        self.tags = [str(tag).lstrip("#") for tag in (tags or []) if str(tag).strip()]
        self.account_file = str(account_file)
        self.description = str(description or "")
        self.headless = headless

    @property
    def caption(self) -> str:
        suffix = " ".join(f"#{tag}" for tag in self.tags)
        return "\n\n".join(
            part
            for part in (self.title.strip(), self.description.strip(), suffix)
            if part
        )

    async def publish(self, page: Page) -> None:
        raise NotImplementedError

    async def upload(self, playwright: Playwright) -> None:
        if not Path(self.file_path).is_file():
            raise FileNotFoundError(f"Video file does not exist: {self.file_path}")
        if not await _browser_cookie_auth(playwright, self.platform_type, self.account_file):
            raise RuntimeError(f"{_config(self.platform_type)['name']} 登录态失效，请重新登录")
        context, browser = await _open_account_context(
            playwright, self.account_file, headless=self.headless
        )
        context = await set_init_script(context)
        page = await context.new_page()
        await page.set_viewport_size({"width": 1440, "height": 1000})
        page.set_default_timeout(60000)
        try:
            await self.publish(page)
            try:
                await asyncio.wait_for(context.storage_state(
                    path=chrome_storage_state_path(self.account_file)
                ), timeout=60)
            except Exception as exc:
                _config(self.platform_type)['logger'].warning(
                    '发布成功，但登录态保存未完成（{}）；请勿重复发布', type(exc).__name__)
        except Exception as exc:
            _config(self.platform_type)['logger'].error(
                '发布失败 [{}] {}: {}', getattr(self, '_publish_stage', '发布流程'),
                type(exc).__name__, str(exc))
            failure_dir = Path(BASE_DIR) / "logs" / "failures"
            failure_dir.mkdir(parents=True, exist_ok=True)
            try:
                await asyncio.wait_for(page.screenshot(
                    path=str(failure_dir / f"{self.platform_slug}-publish-failed.png"),
                    full_page=True,
                ), timeout=10)
            except Exception:
                pass
            raise
        finally:
            await _close_account_context(context, browser)

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)


class XWebVideo(BrowserVideoPublisher):
    platform_type = 7
    platform_slug = "x"

    async def publish(self, page: Page) -> None:
        await page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=120000)
        # Prefer the modal over the still-mounted home timeline composer.
        dialog = page.get_by_role("dialog").filter(
            has=page.locator('[data-testid="tweetTextarea_0"]')
        ).locator('visible=true').first
        editor = await _first_visible(
            [
                dialog.locator('[data-testid="tweetTextarea_0"]'),
                page.locator('[data-testid="tweetTextarea_0"]'),
                page.locator('[role="textbox"][contenteditable="true"]'),
            ]
        )
        await editor.fill(self.caption[:280])
        # The home timeline can keep another editor/Post button behind the modal.
        composer = dialog if await dialog.is_visible() else page
        file_input = composer.locator('input[data-testid="fileInput"], input[type="file"]').first
        await file_input.wait_for(state="attached", timeout=30000)
        await file_input.set_input_files(self.file_path, timeout=PROCESSING_TIMEOUT_MS)
        button = composer.locator(
            '[data-testid="tweetButton"], [data-testid="tweetButtonInline"]'
        )
        await (await _wait_enabled(button, timeout=PROCESSING_TIMEOUT_MS)).click(timeout=PROCESSING_TIMEOUT_MS)
        try:
            await editor.wait_for(state="hidden", timeout=PROCESSING_TIMEOUT_MS)
        except Exception:
            raise RuntimeError("X 发布后编辑器仍未关闭，未确认发布成功")
        x_logger.success("X 视频发布成功")


class InstagramWebVideo(BrowserVideoPublisher):
    platform_type = 8
    platform_slug = "instagram"

    @property
    def publication_caption(self) -> str:
        # Instagram uses one caption for the title, description and hashtags.
        # Never truncate the tail silently: that can discard the requested topics.
        tags = [tag.strip().lstrip('#').strip() for tag in self.tags]
        caption = '\n\n'.join(part for part in (
            self.title.strip(), self.description.strip(),
            ' '.join(f'#{tag}' for tag in tags if tag),
        ) if part)
        if len(caption) > 2200:
            raise ValueError('Instagram 标题、正文和话题合计超过 2200 字符，请缩短后发布')
        return caption

    def publish_stage(self, stage):
        self._publish_stage = stage
        instagram_logger.info('Instagram 发布步骤：{}', stage)

    async def open_composer(self, page: Page, timeout=PROCESSING_TIMEOUT_MS) -> Locator:
        self.publish_stage('打开首页')
        await page.goto(
            "https://www.instagram.com/",
            wait_until="domcontentloaded",
            timeout=120000,
        )
        # The /create/select/ route resolves to the @create profile on the web.
        # Open the real composer through the navigation instead.
        later = page.get_by_role("button", name=re.compile(r"^(Not Now|以后再说|暂不)$", re.I))
        try:
            await later.click(timeout=5000)
        except PlaywrightTimeoutError:
            pass
        self.publish_stage('打开新建帖子')
        create = await _first_visible([
            page.locator('svg[aria-label="新帖子"], svg[aria-label="新建帖子"], svg[aria-label="New post"]'),
            page.get_by_role("link", name=re.compile(r"^(Create|创建)$", re.I)),
        ], timeout=timeout)
        await create.click(timeout=timeout)
        self.publish_stage('等待新建帖子加载上传控件')
        # The modal can remain on a spinner long after the Create click succeeds.
        # Wait for its file input without reopening the modal or refreshing the page.
        file_input = page.locator('input[type="file"][accept*="video"]').first
        try:
            await file_input.wait_for(state="attached", timeout=timeout)
        except PlaywrightTimeoutError as exc:
            raise RuntimeError('Instagram 新建帖子未在等待时限内加载完成，视频尚未上传或发布') from exc
        return file_input

    @staticmethod
    async def enabled_dialog_action(dialog, names):
        # Ignore background controls and disabled duplicates, including aria-disabled
        # on a wrapping control. Instagram also renders links/divs with role=button.
        for locator in (dialog.get_by_role('button', name=names),
                        dialog.get_by_role('link', name=names)):
            for button in await locator.all():
                disabled = button.locator('xpath=ancestor-or-self::*[@disabled or @aria-disabled="true"]')
                if await button.is_visible() and await button.is_enabled() and not await disabled.count():
                    return button
        return None

    async def prepare_caption(self, page: Page, timeout=PROCESSING_TIMEOUT_MS) -> Locator:
        expected_caption = self.publication_caption
        deadline = asyncio.get_running_loop().time() + timeout / 1000
        next_names = re.compile(r'^\s*(?:Next|Continue|下一步|继续|繼續|下一页|下一頁)\s*$', re.I)
        stage_names = re.compile(r'^\s*(?:Crop|Edit|裁剪|裁切|剪裁|编辑|編輯)\s*$', re.I)
        previous_button = None
        previous_stage = ''
        advances = 0
        self.publish_stage('等待裁剪页的下一步')
        while asyncio.get_running_loop().time() < deadline:
            remaining = max(1, int((deadline - asyncio.get_running_loop().time()) * 1000))
            dialogs = page.get_by_role('dialog').locator('visible=true')
            onboarding = dialogs.filter(has_text=re.compile(
                r'视频帖现在会以 Reels|影片貼文.*Reels|Video posts.*reels', re.I
            )).last
            if await onboarding.is_visible():
                dismiss = await self.enabled_dialog_action(onboarding, re.compile(
                    r'^\s*(?:确定|確定|OK|Got it)\s*$', re.I))
                if dismiss is not None:
                    await dismiss.click(timeout=min(5000, remaining))
                    await onboarding.wait_for(state='hidden', timeout=remaining)
                await asyncio.sleep(0.1)
                continue
            # Work only inside the foreground composer, not the homepage textboxes.
            dialog = dialogs.last
            if await dialog.is_visible():
                for caption in await dialog.locator(
                    '[contenteditable="true"][role="textbox"], textarea'
                ).all():
                    if await caption.is_visible() and await caption.is_editable():
                        self.publish_stage('填写标题、正文和话题')
                        await caption.fill(expected_caption, timeout=remaining)
                        return caption
                button = await self.enabled_dialog_action(dialog, next_names)
                if button is not None and advances < 2:
                    headings = dialog.get_by_text(stage_names).locator('visible=true')
                    stage = (await headings.first.inner_text()).strip() if await headings.count() else ''
                    # A slow transition may leave the old Next enabled. Do not click
                    # it twice; wait for a changed stage or disappearance of that node.
                    unchanged = previous_button is not None and (
                        bool(stage and stage == previous_stage) or
                        (not stage and await previous_button.is_visible())
                    )
                    if not unchanged:
                        previous_button = await button.element_handle()
                        previous_stage = stage
                        self.publish_stage(f'自动点击{stage or ("裁剪" if advances == 0 else "编辑")}页下一步')
                        await button.click(timeout=min(5000, remaining))
                        advances += 1
            await asyncio.sleep(0.15)
        raise TimeoutError('Instagram 裁剪/编辑未进入文案页，未点击分享；请检查失败截图和步骤日志')

    async def submit_caption(self, caption: Locator, timeout=PROCESSING_TIMEOUT_MS):
        expected = self.publication_caption
        dialog = caption.locator('xpath=ancestor::*[@role="dialog"][1]')
        # Commit the editor and move focus away from hashtag suggestions.
        await caption.press('Tab', timeout=timeout)
        deadline = asyncio.get_running_loop().time() + timeout / 1000
        names = re.compile(r'^\s*(?:Share|Publish|分享|发布|發佈|發表)\s*$', re.I)
        while asyncio.get_running_loop().time() < deadline:
            if await caption.is_visible() and await dialog.is_visible():
                button = await self.enabled_dialog_action(dialog, names)
                if button is not None:
                    actual = await caption.evaluate(
                        '(element) => element.tagName === "TEXTAREA" ? element.value : element.innerText'
                    )
                    # Chromium's contenteditable innerText can add an extra newline
                    # for a blank <div><br></div>; compare content, not that rendering artifact.
                    normalize = lambda text: re.sub(r'\n+', '\n', text.replace('\r\n', '\n')).strip()
                    if normalize(actual) != normalize(expected):
                        raise RuntimeError('Instagram 标题或话题填写后发生变化，未点击分享')
                    remaining = max(1, int((deadline - asyncio.get_running_loop().time()) * 1000))
                    self.publish_stage('点击分享')
                    await button.click(timeout=remaining)
                    return  # A result timeout must never retry the submission.
            await asyncio.sleep(0.2)
        raise TimeoutError('Instagram 当前发布窗口的分享按钮未就绪，未点击分享')

    async def publish(self, page: Page) -> None:
        self.publication_caption  # Validate before opening/uploading the video.
        self.publish_stage('打开编辑器')
        file_input = await self.open_composer(page)
        self.publish_stage('上传视频')
        await file_input.set_input_files(self.file_path, timeout=PROCESSING_TIMEOUT_MS)
        self.publish_stage('编辑视频和文案')
        caption = await self.prepare_caption(page)
        self.publish_stage('核对标题和话题，等待分享按钮')
        await self.submit_caption(caption, timeout=PROCESSING_TIMEOUT_MS)
        self.publish_stage('确认分享结果')
        await self.wait_share_result(page)
        instagram_logger.success("Instagram 视频发布成功")

    async def wait_share_result(self, page: Page, timeout=PROCESSING_TIMEOUT_MS):
        # Match complete completion messages, not arbitrary feed text containing 已分享.
        dialog = page.get_by_role('dialog').locator('visible=true')
        success = await _first_visible(
            [
                dialog.get_by_text(re.compile(
                    r"^(?:Your (?:reel|post) has been shared[.!]?|"
                    r"你的\s*(?:Reels?|帖子|贴文|貼文)\s*已(?:分享|共享|发布|發佈)[。！!]?|"
                    r"分享了\s*Reels|已分享|已发布)$", re.I)),
            ],
            timeout=timeout,
        )
        if not await success.is_visible():
            raise RuntimeError("Instagram 未返回发布成功提示")


class FacebookWebVideo(BrowserVideoPublisher):
    platform_type = 9
    platform_slug = "facebook"

    async def publish(self, page: Page) -> None:
        await page.goto(
            "https://www.facebook.com/reels/create/",
            wait_until="domcontentloaded",
            timeout=120000,
        )
        file_input = page.locator('input[type="file"]').first
        await file_input.wait_for(state="attached", timeout=30000)
        await file_input.set_input_files(self.file_path, timeout=PROCESSING_TIMEOUT_MS)
        next_labels = ["Next", "下一步", "下一页", "下一頁"]
        await _click_text(page, next_labels, timeout=PROCESSING_TIMEOUT_MS)
        try:
            await _click_text(page, next_labels, timeout=30000)
        except TimeoutError:
            pass
        description = await _first_visible(
            [
                page.locator('[aria-label*="Describe your reel" i][contenteditable="true"]'),
                page.locator('[role="textbox"][contenteditable="true"]'),
                page.locator("textarea"),
            ],
            timeout=60000,
        )
        await description.fill(self.caption[:5000])
        await _click_text(page, ["Publish", "Post", "Share", "发布", "發佈", "分享"], timeout=PROCESSING_TIMEOUT_MS)
        deadline = asyncio.get_running_loop().time() + PROCESSING_TIMEOUT_MS / 1000
        while asyncio.get_running_loop().time() < deadline:
            if "/reels/create" not in page.url or not await description.is_visible():
                break
            await asyncio.sleep(1)
        else:
            raise RuntimeError("Facebook 发布页未关闭，未确认发布成功")
        facebook_logger.success("Facebook Reel 发布成功")
