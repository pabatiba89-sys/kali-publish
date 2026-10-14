from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import Page, Playwright, async_playwright, TimeoutError as PlaywrightTimeoutError

from conf import LOCAL_CHROME_HEADLESS
from utils.browser_runtime import chromium_launch_options
from utils.log import alipay_logger
from utils.publish_lifecycle import close_owned_browser, navigation_read


ALIPAY_PORTAL_HOME = "https://c.alipay.com/page/portal/home"
ALIPAY_LIFE_ACCOUNT_URL = (
    "https://c.alipay.com/page/life-account/index"
    "?_appScene=CONTENT&appId=2030022469359777"
)
ALIPAY_TIMEZONE = timezone(timedelta(hours=8))


def normalize_publish_date(value, *, now=None) -> datetime:
    """Validate native scheduling, interpreting timezone-less input as Beijing time."""
    try:
        target = value if isinstance(value, datetime) else datetime.fromisoformat(
            str(value).strip().replace("Z", "+00:00")
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("支付宝定时发布时间不能为空，格式为 YYYY-MM-DD HH:mm") from exc
    target = (target.replace(tzinfo=ALIPAY_TIMEZONE) if target.tzinfo is None
              else target.astimezone(ALIPAY_TIMEZONE))
    if target.second or target.microsecond:
        raise ValueError("支付宝定时发布时间仅支持整分钟，请将秒和毫秒设为 0")
    current = now if now is not None else datetime.now(ALIPAY_TIMEZONE)
    if current.tzinfo is None:
        current = current.replace(tzinfo=ALIPAY_TIMEZONE)
    if not timedelta(minutes=15) <= target - current <= timedelta(days=14):
        raise ValueError("支付宝定时时间须为当前时间后 15 分钟至 14 天，请预留登录和上传耗时")
    return target


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
    context = None
    try:
        context = await browser.new_context(storage_state=account_path)
        page = await context.new_page()
        await page.goto(
            ALIPAY_LIFE_ACCOUNT_URL,
            wait_until="domcontentloaded",
            timeout=120000,
        )
        await page.wait_for_timeout(5000)
        # The portal can retain a hidden login iframe after a successful scan.
        # Verify the publishing entry rather than rejecting any iframe node.
        visible_login = await navigation_read(page.locator('iframe[title="login"]:visible').count)
        entry = page.locator('a:has-text("发布视频")').first
        return (urlsplit(page.url).hostname == 'c.alipay.com'
                and not visible_login
                and await navigation_read(entry.is_visible)
                and await navigation_read(entry.is_enabled))
    except Exception:
        return False
    finally:
        await close_owned_browser(context, browser, alipay_logger)


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
        publish_date=None,
    ):
        self.title = str(title or "")
        self.file_path = str(file_path)
        self.tags = list(tags or [])
        self.account_file = str(account_file)
        self.desc = str(desc or "")
        self.thumbnail_path = str(thumbnail_path) if thumbnail_path else None
        self.collection_name = collection_name
        self.headless = headless
        self.publish_date = normalize_publish_date(publish_date) if publish_date is not None else None

    async def login_for_publish(self, page: Page, timeout: float = 900) -> None:
        """Reauthenticate in the task-owned page without saving or closing it.

        Standalone account registration owns a separate browser lifecycle. Never
        call alipay_cookie_gen here: this page must survive until publication.
        """
        await page.goto(ALIPAY_PORTAL_HOME, wait_until="domcontentloaded", timeout=120000)
        alipay_logger.info("请在当前发布窗口扫码登录支付宝，登录后将继续上传，不会关闭窗口")
        deadline = time.monotonic() + timeout
        saw_login = False
        settled_since = None
        while time.monotonic() < deadline:
            if page.is_closed():
                raise RuntimeError("支付宝发布登录窗口已关闭，本次视频尚未发布")
            url = urlsplit(page.url)
            login_visible = await navigation_read(page.locator('iframe[title="login"]:visible').count)
            if login_visible or url.hostname == "auth.alipay.com" or "login" in url.path.lower():
                saw_login = True
                settled_since = None
            elif url.hostname == "c.alipay.com":
                entry = page.locator('a:has-text("发布视频")').first
                if settled_since is None:
                    settled_since = time.monotonic()
                if (await navigation_read(entry.is_visible) and await navigation_read(entry.is_enabled)) or (
                    saw_login and time.monotonic() - settled_since >= 2
                ):
                    # The caller must still open and validate the upload page
                    # before touching the video or reporting login success.
                    return
            else:
                settled_since = None
            await asyncio.sleep(0.25)
        raise RuntimeError("支付宝生活号登录未完成或已超时，本次视频尚未发布")

    async def open_upload_page(self, page: Page, timeout: float = 900) -> None:
        try:
            await asyncio.wait_for(self._open_upload_page(page), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise RuntimeError("支付宝登录或发布页等待超时（最长15分钟），视频尚未提交") from exc

    async def _open_upload_page(self, page: Page) -> None:
        await page.goto(
            ALIPAY_LIFE_ACCOUNT_URL,
            wait_until="domcontentloaded",
            timeout=120000,
        )
        saw_login = False
        settled_since = None
        entry_clicked = False
        while True:
            if page.is_closed():
                raise RuntimeError("支付宝发布窗口已关闭，视频尚未提交")
            url = urlsplit(page.url)
            login_visible = await navigation_read(page.locator('iframe[title="login"]:visible').count)
            if login_visible or url.hostname == "auth.alipay.com" or "login" in url.path.lower():
                if not saw_login:
                    alipay_logger.info("发布页要求重新登录，请在当前窗口扫码；完成后继续本次发布")
                saw_login = True
                settled_since = None
                entry_clicked = False
            elif url.hostname == "c.alipay.com":
                if "/content-creation/publish/short-video" in url.path:
                    if await navigation_read(page.locator('input[type="file"]').count):
                        return
                else:
                    entry = page.locator('a:has-text("发布视频")').first
                    if not entry_clicked and await navigation_read(entry.is_visible) and await navigation_read(entry.is_enabled):
                        try:
                            await entry.click(timeout=1000)
                            entry_clicked = True
                        except PlaywrightTimeoutError:
                            # The login overlay can appear between detection and click.
                            pass
                    elif saw_login and not entry_clicked:
                        if settled_since is None:
                            settled_since = time.monotonic()
                        elif time.monotonic() - settled_since >= 2:
                            # Scan redirects to the portal, not necessarily the life account.
                            # Navigate only after it settles, never refresh an active QR code.
                            saw_login = False
                            settled_since = None
                            await page.goto(ALIPAY_LIFE_ACCOUNT_URL, wait_until="domcontentloaded", timeout=120000)
            else:
                settled_since = None
            await asyncio.sleep(0.25)

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

    async def upload_thumbnail(self, page: Page, timeout: int = 180000) -> None:
        if self.thumbnail_path and not Path(self.thumbnail_path).is_file():
            raise FileNotFoundError(f"Thumbnail does not exist: {self.thumbnail_path}")
        try:
            cover = page.get_by_text("上传封面", exact=True).locator("visible=true").first
            await cover.scroll_into_view_if_needed(timeout=timeout)
            await cover.click(timeout=timeout)
            # Even without a custom image, the default video frame must be
            # accepted. Include the footer, not just the modal body.
            modal = page.locator('.antd5-modal:visible, [role="dialog"]:visible').last
            await modal.wait_for(state="visible", timeout=timeout)
            if self.thumbnail_path:
                inner = modal.get_by_text("上传封面", exact=True).first
                if await inner.is_visible():
                    await inner.click(timeout=timeout)
                upload = modal.get_by_role("button", name="上传图片", exact=True).first
                await upload.click(timeout=timeout)
                image_input = modal.locator(
                    'input[type="file"][accept*="jpg"], '
                    'input[type="file"][accept*="png"], '
                    'input[type="file"][accept*="image"]'
                ).first
                await image_input.wait_for(state="attached", timeout=timeout)
                await image_input.set_input_files(self.thumbnail_path, timeout=timeout)
            done = modal.get_by_role(
                "button", name=re.compile(r"^(确\s*认|确\s*定|完\s*成)$")
            ).first
            await done.click(timeout=timeout)
            await modal.wait_for(state="hidden", timeout=timeout)
            alipay_logger.success("支付宝生活号封面已确认")
        except Exception as exc:
            raise RuntimeError("支付宝生活号封面未确认，已停止发布") from exc

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

    async def verify_schedule(self, page: Page) -> None:
        if self.publish_date is None:
            return
        # Login and upload can consume minutes: validate again at final submit.
        target = normalize_publish_date(self.publish_date)
        radio = page.get_by_role("radio", name=re.compile(r"^\s*定时发布\s*$"))
        date = page.get_by_placeholder("请选择日期", exact=True)
        if (await radio.count() != 1 or not await radio.is_checked()
                or await date.count() != 1 or not await date.is_visible()
                or await date.input_value() != target.strftime("%Y-%m-%d %H:%M")):
            raise RuntimeError("支付宝定时选项或时间与请求不一致，已停止发布")
        if await page.locator(
            '.antd5-picker-dropdown:visible, .ant-picker-dropdown:visible, '
            '.antd5-form-item-explain-error:visible, .ant-form-item-explain-error:visible'
        ).count():
            raise RuntimeError("支付宝定时时间尚未确认或表单校验失败，已停止发布")

    async def apply_schedule(self, page: Page, timeout: int = 30000) -> None:
        if self.publish_date is None:
            return
        target = normalize_publish_date(self.publish_date)
        try:
            radio = page.get_by_role("radio", name=re.compile(r"^\s*定时发布\s*$"))
            if not await radio.is_visible():
                await page.get_by_text("展开", exact=True).locator("visible=true").click(timeout=timeout)
            await radio.check(timeout=timeout)
            date = page.get_by_placeholder("请选择日期", exact=True)
            await date.click(timeout=timeout)
            await date.fill(target.strftime("%Y-%m-%d %H:%M"), timeout=timeout)
            picker = page.locator('.antd5-picker-dropdown:visible, .ant-picker-dropdown:visible')
            await picker.get_by_role("button", name=re.compile(r"^确\s*定$")).click(timeout=timeout)
            await picker.wait_for(state="hidden", timeout=timeout)
            # Blurring catches controlled inputs that revert an unaccepted value.
            await date.blur(timeout=timeout)
            await self.verify_schedule(page)
        except ValueError:
            raise
        except Exception as exc:
            raise RuntimeError("支付宝定时发布时间设置或确认失败，已停止发布") from exc
        alipay_logger.info(f"支付宝定时发布已设置：{target:%Y-%m-%d %H:%M}（北京时间）")

    async def submit(self, page: Page, timeout: float = 120) -> None:
        await self.verify_schedule(page)
        button = page.get_by_role("button", name="确认发布").first
        await button.click()
        started = time.monotonic()
        continued = False
        while time.monotonic() - started < timeout:
            # Check completion BEFORE any "继续发布" control: on a result
            # screen that control can mean publishing another video.
            if "/content-creation/posts" in page.url:
                return
            result = page.get_by_text(
                re.compile(r"^(?:视频|作品)?(?:发布成功|提交成功)[！!。]?$"),
            ).locator("visible=true")
            if await navigation_read(result.count):
                return
            success = page.locator(
                '.antd5-message-notice-content:has-text("发布成功"), '
                '.antd5-message-notice-content:has-text("提交成功"), '
                '.antd5-message-notice-content:has-text("审核中")'
            ).locator("visible=true")
            if await navigation_read(success.count):
                return
            continue_button = page.locator(
                '.antd5-modal-wrap button:has-text("继续发布"), '
                '.antd5-modal button:has-text("继续发布")'
            ).locator("visible=true").first
            if not continued and await navigation_read(continue_button.is_visible):
                if self.publish_date is not None:
                    normalize_publish_date(self.publish_date)
                await continue_button.click()
                continued = True
            await asyncio.sleep(0.25)
        raise RuntimeError("支付宝生活号未返回发布成功信号")

    async def upload(self, playwright: Playwright) -> None:
        if not Path(self.file_path).is_file():
            raise FileNotFoundError(f"Video file does not exist: {self.file_path}")
        has_saved_state = Path(self.account_file).is_file()
        # Reuse saved state in the actual publishing session. A separate headless
        # probe can misclassify a slow page, or rotate cookies that it never saves.
        # Keep this window visible so a genuine login redirect can be handled here.
        browser = await playwright.chromium.launch(
            **chromium_launch_options(headless=False)
        )
        context = None
        stage = "创建发布会话"
        try:
            options = {"storage_state": self.account_file} if has_saved_state else {}
            context = await browser.new_context(**options)
            page = await context.new_page()
            if not has_saved_state:
                stage = "扫码重新登录"
                await self.login_for_publish(page)
            else:
                alipay_logger.info("在本次发布窗口复用已保存登录态，仅在平台要求时扫码")
            stage = "进入发布页"
            await self.open_upload_page(page)
            if not has_saved_state:
                alipay_logger.info("支付宝生活号重新登录成功，已进入发布页，继续本次发布")
            stage = "填写视频和封面"
            await self.fill_form(page)
            stage = "等待视频上传"
            await self.wait_upload(page)
            stage = "设置发布时间"
            await self.apply_schedule(page)
            stage = "提交并确认发布结果"
            await self.submit(page)
            alipay_logger.success("支付宝生活号定时任务提交成功" if self.publish_date else "支付宝生活号视频发布成功")
            try:
                await asyncio.wait_for(context.storage_state(path=self.account_file), timeout=60)
                alipay_logger.success("支付宝发布后登录态已更新到原账号文件")
            except Exception:
                alipay_logger.warning("发布已成功，但登录态刷新未完成；继续关闭发布窗口")
        except Exception as exc:
            alipay_logger.error("支付宝发布失败 [{}] {}: {}", stage, type(exc).__name__, str(exc))
            raise
        finally:
            await close_owned_browser(context, browser, alipay_logger)

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)
