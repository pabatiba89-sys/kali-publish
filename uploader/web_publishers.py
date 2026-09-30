from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import Locator, Page, Playwright, async_playwright

from conf import BASE_DIR, LOCAL_CHROME_HEADLESS
from utils.base_social_media import set_init_script
from utils.browser_runtime import chromium_launch_options
from utils.log import facebook_logger, instagram_logger, x_logger


WEB_PLATFORMS = {
    7: {
        "name": "X",
        "login_url": "https://x.com/i/flow/login",
        "home_url": "https://x.com/home",
        "cookies": {"auth_token"},
        "logger": x_logger,
    },
    8: {
        "name": "Instagram",
        "login_url": "https://www.instagram.com/accounts/login/",
        "home_url": "https://www.instagram.com/",
        "cookies": {"sessionid"},
        "logger": instagram_logger,
    },
    9: {
        "name": "Facebook",
        "login_url": "https://www.facebook.com/login/",
        "home_url": "https://www.facebook.com/",
        "cookies": {"c_user", "xs"},
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


async def browser_cookie_gen(platform_type: int, account_file) -> dict:
    """Open installed Chrome for interactive sign-in and save Playwright storage state."""
    config = _config(platform_type)
    destination = Path(account_file)
    destination.parent.mkdir(parents=True, exist_ok=True)
    logger = config["logger"]
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**chromium_launch_options(headless=False))
        context = await browser.new_context()
        context = await set_init_script(context)
        page = await context.new_page()
        await page.goto(config["login_url"], wait_until="domcontentloaded", timeout=120000)
        logger.info(f"请在弹出的 Chrome 窗口完成 {config['name']} 登录")
        success = False
        try:
            for _ in range(600):
                if await _has_login_cookies(context, config["cookies"]):
                    await page.goto(config["home_url"], wait_until="domcontentloaded", timeout=120000)
                    await page.wait_for_timeout(2000)
                    if "login" not in page.url.lower():
                        success = True
                        break
                await asyncio.sleep(1)
            if success:
                await context.storage_state(path=destination)
                try:
                    destination.chmod(0o600)
                except OSError:
                    pass
        finally:
            current_url = page.url
            await context.close()
            await browser.close()
    return {
        "success": success,
        "status": "logged_in" if success else "timeout",
        "message": "登录成功" if success else "登录未完成或已超时",
        "account_file": str(destination),
        "current_url": current_url,
    }


async def _browser_cookie_auth(playwright: Playwright, platform_type: int, account_file) -> bool:
    config = _config(platform_type)
    account_path = Path(account_file)
    if not account_path.is_file():
        return False
    browser = await playwright.chromium.launch(**chromium_launch_options(headless=True))
    try:
        context = await browser.new_context(storage_state=account_path)
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
        await browser.close()


async def browser_cookie_auth(platform_type: int, account_file) -> bool:
    async with async_playwright() as playwright:
        return await _browser_cookie_auth(playwright, platform_type, account_file)


async def _first_visible(locators: list[Locator], timeout: int = 30000) -> Locator:
    deadline = asyncio.get_running_loop().time() + timeout / 1000
    while asyncio.get_running_loop().time() < deadline:
        for locator in locators:
            try:
                if await locator.count() and await locator.first.is_visible():
                    return locator.first
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
    await locator.click()


async def _wait_enabled(locator: Locator, timeout: int = 180000) -> Locator:
    deadline = asyncio.get_running_loop().time() + timeout / 1000
    while asyncio.get_running_loop().time() < deadline:
        try:
            if await locator.count() and await locator.first.is_visible():
                disabled = await locator.first.get_attribute("disabled")
                aria_disabled = await locator.first.get_attribute("aria-disabled")
                if disabled is None and aria_disabled != "true":
                    return locator.first
        except Exception:
            pass
        await asyncio.sleep(1)
    raise TimeoutError("Publish button did not become enabled")


class BrowserVideoPublisher:
    platform_type: int
    platform_slug: str

    def __init__(self, title, file_path, tags, account_file, headless=LOCAL_CHROME_HEADLESS):
        self.title = str(title or "")
        self.file_path = str(file_path)
        self.tags = [str(tag).lstrip("#") for tag in (tags or []) if str(tag).strip()]
        self.account_file = str(account_file)
        self.headless = headless

    @property
    def caption(self) -> str:
        suffix = " ".join(f"#{tag}" for tag in self.tags)
        return "\n\n".join(part for part in (self.title.strip(), suffix) if part)

    async def publish(self, page: Page) -> None:
        raise NotImplementedError

    async def upload(self, playwright: Playwright) -> None:
        if not Path(self.file_path).is_file():
            raise FileNotFoundError(f"Video file does not exist: {self.file_path}")
        if not await _browser_cookie_auth(playwright, self.platform_type, self.account_file):
            raise RuntimeError(f"{_config(self.platform_type)['name']} 登录态失效，请重新登录")
        browser = await playwright.chromium.launch(
            **chromium_launch_options(headless=self.headless)
        )
        context = await browser.new_context(storage_state=self.account_file)
        context = await set_init_script(context)
        page = await context.new_page()
        page.set_default_timeout(60000)
        try:
            await self.publish(page)
            await context.storage_state(path=self.account_file)
        except Exception:
            failure_dir = Path(BASE_DIR) / "logs" / "failures"
            failure_dir.mkdir(parents=True, exist_ok=True)
            try:
                await page.screenshot(
                    path=str(failure_dir / f"{self.platform_slug}-publish-failed.png"),
                    full_page=True,
                )
            except Exception:
                pass
            raise
        finally:
            await context.close()
            await browser.close()

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)


class XWebVideo(BrowserVideoPublisher):
    platform_type = 7
    platform_slug = "x"

    async def publish(self, page: Page) -> None:
        await page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=120000)
        editor = await _first_visible(
            [
                page.locator('[data-testid="tweetTextarea_0"]'),
                page.locator('[role="textbox"][contenteditable="true"]'),
            ]
        )
        await editor.fill(self.caption[:280])
        file_input = page.locator('input[data-testid="fileInput"], input[type="file"]').first
        await file_input.wait_for(state="attached", timeout=30000)
        await file_input.set_input_files(self.file_path)
        button = page.locator(
            '[data-testid="tweetButton"], [data-testid="tweetButtonInline"]'
        )
        await (await _wait_enabled(button, timeout=600000)).click()
        try:
            await editor.wait_for(state="hidden", timeout=60000)
        except Exception:
            raise RuntimeError("X 发布后编辑器仍未关闭，未确认发布成功")
        x_logger.success("X 视频发布成功")


class InstagramWebVideo(BrowserVideoPublisher):
    platform_type = 8
    platform_slug = "instagram"

    async def publish(self, page: Page) -> None:
        await page.goto(
            "https://www.instagram.com/create/select/",
            wait_until="domcontentloaded",
            timeout=120000,
        )
        file_input = page.locator('input[type="file"]').first
        await file_input.wait_for(state="attached", timeout=30000)
        await file_input.set_input_files(self.file_path)
        await _click_text(page, ["Next", "下一步"], timeout=120000)
        try:
            await _click_text(page, ["Next", "下一步"], timeout=30000)
        except TimeoutError:
            pass
        caption = await _first_visible(
            [
                page.locator('textarea[aria-label*="caption" i]'),
                page.locator('textarea[placeholder*="caption" i]'),
                page.locator('textarea'),
            ],
            timeout=60000,
        )
        await caption.fill(self.caption[:2200])
        await _click_text(page, ["Share", "分享"], timeout=60000)
        success = await _first_visible(
            [
                page.get_by_text("Your reel has been shared", exact=False),
                page.get_by_text("Your post has been shared", exact=False),
                page.get_by_text("已分享", exact=False),
            ],
            timeout=180000,
        )
        if not await success.is_visible():
            raise RuntimeError("Instagram 未返回发布成功提示")
        instagram_logger.success("Instagram 视频发布成功")


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
        await file_input.set_input_files(self.file_path)
        await _click_text(page, ["Next", "下一步"], timeout=120000)
        try:
            await _click_text(page, ["Next", "下一步"], timeout=30000)
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
        await _click_text(page, ["Publish", "发布"], timeout=60000)
        deadline = asyncio.get_running_loop().time() + 180
        while asyncio.get_running_loop().time() < deadline:
            if "/reels/create" not in page.url or not await description.is_visible():
                break
            await asyncio.sleep(1)
        else:
            raise RuntimeError("Facebook 发布页未关闭，未确认发布成功")
        facebook_logger.success("Facebook Reel 发布成功")
