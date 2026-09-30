from __future__ import annotations

import asyncio
import time
from pathlib import Path

from playwright.async_api import Page, Playwright, async_playwright

from conf import LOCAL_CHROME_HEADLESS
from utils.browser_runtime import chromium_launch_options
from utils.log import alipay_logger


ALIPAY_PORTAL_HOME = "https://c.alipay.com/page/portal/home"
ALIPAY_LIFE_ACCOUNT_URL = (
    "https://c.alipay.com/page/life-account/index"
    "?_appScene=CONTENT&appId=2030022469359777"
)


def _login_result(success, status, message, account_file, current_url=""):
    return {
        "success": success,
        "status": status,
        "message": message,
        "account_file": str(account_file),
        "current_url": current_url,
    }


def format_title_with_tags(title: str, tags: list[str], max_length: int = 30) -> str:
    result = str(title or "")[:max_length]
    for tag in tags or []:
        candidate = f"{result} #{str(tag).lstrip('#')}"
        if len(candidate) > max_length:
            break
        result = candidate
    return result


async def _login_complete(page: Page) -> bool:
    try:
        if await page.locator('iframe[title="login"]').count():
            return False
        return (
            page.url.startswith("https://c.alipay.com/")
            and "login" not in page.url.lower()
            and not page.url.startswith("https://auth.alipay.com/")
        )
    except Exception:
        return False


async def alipay_cookie_gen(account_file, headless: bool = False):
    """Open the regular Alipay creator page and wait for QR-code sign-in."""
    destination = Path(account_file)
    destination.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            **chromium_launch_options(headless=headless)
        )
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(ALIPAY_PORTAL_HOME, wait_until="domcontentloaded", timeout=120000)
        alipay_logger.info("请在弹出的 Chrome 窗口使用支付宝扫码登录生活号")
        success = False
        try:
            login_iframe = page.locator('iframe[title="login"]')
            for _ in range(30):
                if await login_iframe.count():
                    break
                await asyncio.sleep(1)
            else:
                return _login_result(
                    False,
                    "timeout",
                    "未检测到支付宝登录窗口",
                    destination,
                    page.url,
                )
            for _ in range(300):
                if await _login_complete(page):
                    success = True
                    await page.wait_for_timeout(2000)
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
    return _login_result(
        success,
        "logged_in" if success else "timeout",
        "登录成功" if success else "登录未完成或已超时",
        destination,
        current_url,
    )


async def _cookie_auth(playwright: Playwright, account_file) -> bool:
    account_path = Path(account_file)
    if not account_path.is_file():
        return False
    browser = await playwright.chromium.launch(
        **chromium_launch_options(headless=True)
    )
    try:
        context = await browser.new_context(storage_state=account_path)
        page = await context.new_page()
        await page.goto(
            ALIPAY_LIFE_ACCOUNT_URL,
            wait_until="domcontentloaded",
            timeout=120000,
        )
        await page.wait_for_timeout(5000)
        return await _login_complete(page)
    except Exception:
        return False
    finally:
        await browser.close()


async def cookie_auth(account_file) -> bool:
    async with async_playwright() as playwright:
        return await _cookie_auth(playwright, account_file)


async def alipay_setup(account_file, handle=False, return_detail=False, headless=False):
    if not Path(account_file).is_file() or not await cookie_auth(account_file):
        if not handle:
            result = _login_result(
                False, "cookie_invalid", "登录态不存在或已失效", account_file
            )
            return result if return_detail else False
        result = await alipay_cookie_gen(account_file, headless=headless)
        return result if return_detail else result["success"]
    result = _login_result(True, "cookie_valid", "登录态有效", account_file)
    return result if return_detail else True


class AlipayVideo:
    def __init__(
        self,
        title,
        file_path,
        tags,
        account_file,
        desc="",
        thumbnail_path=None,
        collection_name=None,
        headless=LOCAL_CHROME_HEADLESS,
    ):
        self.title = str(title or "")
        self.file_path = str(file_path)
        self.tags = list(tags or [])
        self.account_file = str(account_file)
        self.desc = str(desc or "")
        self.thumbnail_path = str(thumbnail_path) if thumbnail_path else None
        self.collection_name = collection_name
        self.headless = headless

    async def open_upload_page(self, page: Page) -> None:
        await page.goto(
            ALIPAY_LIFE_ACCOUNT_URL,
            wait_until="domcontentloaded",
            timeout=120000,
        )
        entry = page.locator('a:has-text("发布视频")').first
        await entry.wait_for(state="visible", timeout=60000)
        await entry.click()
        await page.wait_for_url("**/content-creation/publish/short-video**", timeout=60000)

    async def fill_form(self, page: Page) -> None:
        file_input = page.locator('input[type="file"]').first
        await file_input.wait_for(state="attached", timeout=30000)
        await file_input.set_input_files(self.file_path)

        title = page.get_by_placeholder("一个好的标题，能获得更多人的喜欢哦").first
        await title.wait_for(state="visible", timeout=30000)
        await title.fill(format_title_with_tags(self.title, self.tags))

        if self.desc:
            description = page.get_by_placeholder("填写作品描述，让你的作品更容易被看到").first
            if await description.count():
                await description.fill(self.desc)

        await self.upload_thumbnail(page)
        await self.apply_collection(page)

        ai_label = page.locator('label.antd5-radio-wrapper', has_text="内容由AI生成").first
        if await ai_label.count():
            radio = ai_label.locator('input[type="radio"]').first
            await radio.check()

    async def upload_thumbnail(self, page: Page) -> None:
        if not self.thumbnail_path:
            return
        if not Path(self.thumbnail_path).is_file():
            raise FileNotFoundError(f"Thumbnail does not exist: {self.thumbnail_path}")
        try:
            cover = page.get_by_text("上传封面", exact=True).first
            await cover.scroll_into_view_if_needed()
            await cover.click(timeout=10000)
            await page.wait_for_timeout(1500)
            modal = page.locator(".antd5-modal-body").last
            inner = modal.get_by_text("上传封面", exact=True).first
            if await inner.count():
                await inner.click(timeout=8000)
                await page.wait_for_timeout(1000)
            upload = modal.get_by_role("button", name="上传图片").first
            await upload.click(timeout=10000)
            image_input = page.locator(
                'input[type="file"][accept*="jpg"], '
                'input[type="file"][accept*="png"], '
                'input[type="file"][accept*="image"]'
            ).first
            await image_input.wait_for(state="attached", timeout=10000)
            await image_input.set_input_files(self.thumbnail_path)
            done = page.get_by_role("button", name="完 成").first
            if not await done.count():
                done = page.get_by_role("button", name="完成").first
            await done.click(timeout=15000)
            alipay_logger.success("支付宝生活号封面已上传")
        except Exception as exc:
            alipay_logger.warning(f"支付宝生活号封面上传失败，继续发布: {exc}")

    async def apply_collection(self, page: Page) -> None:
        if not self.collection_name:
            return
        try:
            compilation = page.locator('input[id*="_compilationInfo"]').first
            await compilation.scroll_into_view_if_needed()
            selector = compilation.locator("xpath=../../..").first
            await selector.click(timeout=8000)
            options = page.locator('[role="option"]')
            target = options.filter(has_text=self.collection_name).first
            if await target.count():
                await target.click(timeout=5000, force=True)
                alipay_logger.success(f"已选择支付宝合集: {self.collection_name}")
            else:
                await page.keyboard.press("Escape")
                alipay_logger.warning(f"未找到支付宝合集: {self.collection_name}")
        except Exception as exc:
            alipay_logger.warning(f"支付宝合集选择失败，继续发布: {exc}")

    async def wait_upload(self, page: Page, timeout: int = 1800) -> None:
        button = page.get_by_role("button", name="确认发布").first
        started = time.monotonic()
        while time.monotonic() - started < timeout:
            if await button.count() and await button.is_visible() and not await button.is_disabled():
                return
            await asyncio.sleep(2)
        raise TimeoutError("等待支付宝视频上传或转码超时")

    async def submit(self, page: Page) -> None:
        button = page.get_by_role("button", name="确认发布").first
        await button.click()
        started = time.monotonic()
        while time.monotonic() - started < 120:
            continue_button = page.locator(
                '.antd5-modal-wrap button:has-text("继续发布"), '
                '.antd5-modal button:has-text("继续发布")'
            ).first
            if await continue_button.count() and await continue_button.is_visible():
                await continue_button.click()
            if "/content-creation/posts" in page.url:
                return
            success = page.locator(
                '.antd5-message-notice-content:has-text("发布成功"), '
                '.antd5-message-notice-content:has-text("提交成功"), '
                '.antd5-message-notice-content:has-text("审核中")'
            ).first
            if await success.count() and await success.is_visible():
                return
            await asyncio.sleep(1)
        raise RuntimeError("支付宝生活号未返回发布成功信号")

    async def upload(self, playwright: Playwright) -> None:
        if not Path(self.file_path).is_file():
            raise FileNotFoundError(f"Video file does not exist: {self.file_path}")
        if not await _cookie_auth(playwright, self.account_file):
            raise RuntimeError("支付宝生活号登录态失效，请重新登录")
        browser = await playwright.chromium.launch(
            **chromium_launch_options(headless=self.headless)
        )
        context = await browser.new_context(storage_state=self.account_file)
        page = await context.new_page()
        try:
            await self.open_upload_page(page)
            await self.fill_form(page)
            await self.wait_upload(page)
            await self.submit(page)
            await context.storage_state(path=self.account_file)
            alipay_logger.success("支付宝生活号视频发布成功")
        finally:
            await context.close()
            await browser.close()

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)
