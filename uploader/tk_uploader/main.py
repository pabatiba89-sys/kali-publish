# -*- coding: utf-8 -*-
import re
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import Playwright, TimeoutError as PlaywrightTimeoutError, async_playwright
import os
import asyncio
from uploader.tk_uploader.tk_config import Tk_Locator
from utils.base_social_media import set_init_script
from utils.browser_runtime import (
    chrome_profile_has_cookies,
    chrome_storage_state_path,
    chromium_launch_options,
    reserve_loopback_port,
    resolve_chrome_executable,
    save_chrome_storage_state,
)
from utils.log import tiktok_logger
from conf import LOCAL_CHROME_HEADLESS

TIKTOK_LOGIN_URL = "https://www.tiktok.com/login?lang=en"
TIKTOK_STUDIO_URL = "https://www.tiktok.com/tiktokstudio/upload?lang=en"
TIKTOK_LOGIN_COOKIES = {"sessionid"}


def _stop_chrome_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


async def _open_account_context(playwright: Playwright, account_file, headless: bool):
    """Open a dedicated Chrome profile or a legacy storage-state file."""
    account_path = Path(account_file)
    options = chromium_launch_options(headless=headless, args=["--lang=en-GB"])
    if account_path.is_dir():
        storage_state = chrome_storage_state_path(account_path)
        if not storage_state.is_file():
            raise FileNotFoundError(f"TikTok login state is missing: {storage_state}")
    else:
        storage_state = account_path
    browser = await playwright.chromium.launch(**options)
    context = await browser.new_context(storage_state=storage_state)
    return context, browser


async def _close_account_context(context, browser) -> None:
    await context.close()
    if browser is not None:
        await browser.close()


async def tiktok_cookie_gen(account_file) -> dict:
    """Use ordinary Chrome so Google OAuth accepts TikTok sign-in."""
    profile_dir = Path(account_file)
    profile_dir.mkdir(parents=True, exist_ok=True)
    try:
        profile_dir.chmod(0o700)
    except OSError:
        pass

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
            TIKTOK_LOGIN_URL,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    tiktok_logger.info("请在弹出的普通 Chrome 窗口完成 TikTok 登录")
    logged_in = False
    try:
        for _ in range(600):
            if chrome_profile_has_cookies(
                profile_dir, ("tiktok.com",), TIKTOK_LOGIN_COOKIES
            ):
                await asyncio.sleep(2)
                logged_in = await save_chrome_storage_state(
                    debug_port, chrome_storage_state_path(profile_dir)
                )
                break
            if process.poll() is not None:
                logged_in = chrome_profile_has_cookies(
                    profile_dir, ("tiktok.com",), TIKTOK_LOGIN_COOKIES
                )
                if logged_in:
                    logged_in = await save_chrome_storage_state(
                        debug_port, chrome_storage_state_path(profile_dir)
                    )
                break
            await asyncio.sleep(1)
    finally:
        _stop_chrome_process(process)

    return {
        "success": logged_in,
        "status": "logged_in" if logged_in else "timeout",
        "message": "登录成功" if logged_in else "登录未完成或已超时",
        "account_file": str(profile_dir),
        "current_url": TIKTOK_STUDIO_URL if logged_in else "",
    }


async def cookie_auth(account_file):
    async with async_playwright() as playwright:
        context = None
        browser = None
        try:
            context, browser = await _open_account_context(
                playwright, account_file, headless=LOCAL_CHROME_HEADLESS
            )
            context = await set_init_script(context)
            page = await context.new_page()
            await page.goto(TIKTOK_STUDIO_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            names = {cookie.get("name") for cookie in await context.cookies()}
            if not TIKTOK_LOGIN_COOKIES.issubset(names) or "/login" in page.url.lower():
                tiktok_logger.error("[+] cookie expired")
                return False
            # 选择所有的 select 元素
            select_elements = await page.query_selector_all('select')
            for element in select_elements:
                class_name = await element.get_attribute('class')
                # 使用正则表达式匹配特定模式的 class 名称
                if class_name and re.match(r'tiktok-.*-SelectFormContainer.*', class_name):
                    tiktok_logger.error("[+] cookie expired")
                    return False
            tiktok_logger.success("[+] cookie valid")
            return True
        except Exception:
            return False
        finally:
            if context is not None:
                await _close_account_context(context, browser)


async def tiktok_setup(account_file, handle=False):
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            return False
        tiktok_logger.info('[+] cookie file is not existed or expired. Now open the browser auto. Please login with your way(gmail phone, whatever, the cookie file will generated after login')
        await get_tiktok_cookie(account_file)
    return True


async def get_tiktok_cookie(account_file):
    return await tiktok_cookie_gen(account_file)


class TiktokVideo(object):
    def __init__(self, title, file_path, tags, publish_date, account_file, description="", thumbnail_path=None):
        self.title = title
        self.file_path = file_path
        self.tags = tags
        self.publish_date = publish_date
        self.account_file = account_file
        self.description = str(description or "")
        self.thumbnail_path = str(thumbnail_path) if thumbnail_path else None
        self.headless = LOCAL_CHROME_HEADLESS
        self.locator_base = None

    @property
    def caption(self):
        return "\n".join(
            part for part in (str(self.title or "").strip(), self.description.strip()) if part
        )


    async def set_schedule_time(self, page, publish_date):
        schedule_input_element = self.locator_base.get_by_label('Schedule')
        await schedule_input_element.wait_for(state='visible')  # 确保按钮可见

        await schedule_input_element.click(force=True)
        allow_button = self.locator_base.get_by_role("button", name="Allow").first
        if await allow_button.count() and await allow_button.is_visible():
            await allow_button.click()
        scheduled_picker = self.locator_base.locator('div.scheduled-picker')
        await scheduled_picker.locator('div.TUXInputBox').nth(1).click()

        calendar_month = await self.locator_base.locator('div.calendar-wrapper span.month-title').inner_text()

        n_calendar_month = datetime.strptime(calendar_month, '%B').month

        schedule_month = publish_date.month

        if n_calendar_month != schedule_month:
            if n_calendar_month < schedule_month:
                arrow = self.locator_base.locator('div.calendar-wrapper span.arrow').nth(-1)
            else:
                arrow = self.locator_base.locator('div.calendar-wrapper span.arrow').nth(0)
            await arrow.click()

        # day set
        valid_days_locator = self.locator_base.locator(
            'div.calendar-wrapper span.day.valid')
        valid_days = await valid_days_locator.count()
        for i in range(valid_days):
            day_element = valid_days_locator.nth(i)
            text = await day_element.inner_text()
            if text.strip() == str(publish_date.day):
                await day_element.click()
                break
        # time set
        await scheduled_picker.locator('div.TUXInputBox').nth(0).click()

        hour_str = publish_date.strftime("%H")
        correct_minute = int(publish_date.minute / 5) * 5
        minute_str = f"{correct_minute:02d}"

        hour_selector = f"span.tiktok-timepicker-left:has-text('{hour_str}')"
        minute_selector = f"span.tiktok-timepicker-right:has-text('{minute_str}')"

        # pick hour first
        await self.locator_base.locator(hour_selector).click()
        # click time button again
        # 等待某个特定的元素出现或状态变化，表明UI已更新
        await page.wait_for_timeout(1000)  # 等待500毫秒
        await scheduled_picker.locator('div.TUXInputBox').nth(0).click()
        # pick minutes after
        await self.locator_base.locator(minute_selector).click()

        # click title to remove the focus.
        await self.locator_base.locator("h1:has-text('Upload video')").click()

    async def handle_upload_error(self, page):
        tiktok_logger.info("video upload error retrying.")
        select_file_button = self.locator_base.locator('button[aria-label="Select file"]')
        async with page.expect_file_chooser() as fc_info:
            await select_file_button.click()
        file_chooser = await fc_info.value
        await file_chooser.set_files(self.file_path)

    async def upload(self, playwright: Playwright) -> None:
        context, browser = await _open_account_context(
            playwright, self.account_file, headless=self.headless
        )
        try:
            context = await set_init_script(context)
            page = await context.new_page()
            file_input = await self.open_upload_page(page)
            tiktok_logger.info(f'[+]Uploading-------{self.title}.mp4')
            await file_input.set_input_files(self.file_path)
            await self.add_title_tags(page)
            await self.detect_upload_status(page)
            if self.thumbnail_path:
                await self.upload_thumbnail(page)
            if self.publish_date != 0:
                await self.set_schedule_time(page, self.publish_date)
            await self.click_publish(page)
            await context.storage_state(path=chrome_storage_state_path(self.account_file))
        finally:
            await _close_account_context(context, browser)

    async def open_upload_page(self, page):
        try:
            await page.goto(TIKTOK_STUDIO_URL, wait_until="domcontentloaded", timeout=60000)
        except PlaywrightTimeoutError:
            # A slow resource must not abort an already usable upload form.
            tiktok_logger.warning("TikTok 页面加载较慢，继续检查上传控件")
        deadline = asyncio.get_running_loop().time() + 60000 / 1000
        while asyncio.get_running_loop().time() < deadline:
            if "/login" in page.url.lower():
                raise RuntimeError("TikTok 登录态失效，请重新登录")
            for frame in page.frames:
                file_input = frame.locator('input[type="file"][accept*="video"]').first
                if await file_input.count():
                    self.locator_base = frame.locator("body")
                    return file_input
            await asyncio.sleep(0.25)
        raise TimeoutError("TikTok 未出现视频上传控件，请检查页面是否有验证提示")

    async def add_title_tags(self, page):

        editor_locator = self.locator_base.locator('div.public-DraftEditor-content[contenteditable="true"], [contenteditable="true"][role="textbox"]').first
        await editor_locator.wait_for(state="visible", timeout=120000)
        await editor_locator.fill(self.caption)
        await editor_locator.press("End")
        await editor_locator.press("Enter")

        # tag part
        for index, tag in enumerate(self.tags, start=1):
            tiktok_logger.info("Setting the %s tag" % index)
            await page.keyboard.press("End")
            await page.wait_for_timeout(1000)
            await page.keyboard.insert_text("#" + tag + " ")
            await page.keyboard.press("Space")
            await page.wait_for_timeout(1000)
            await page.keyboard.press("Backspace")
            await page.keyboard.press("End")

    async def upload_thumbnail(self, page):
        await self.locator_base.locator(".cover-container").click()
        await self.locator_base.locator(".cover-edit-container").get_by_text(
            "Upload cover", exact=False
        ).click()
        file_input = self.locator_base.locator(
            'input[type="file"][accept*="image"]'
        ).first
        if await file_input.count():
            await file_input.set_input_files(self.thumbnail_path)
        else:
            async with page.expect_file_chooser() as chooser_info:
                await self.locator_base.locator(".upload-image-upload-area").click()
            chooser = await chooser_info.value
            await chooser.set_files(self.thumbnail_path)
        confirm = self.locator_base.locator(
            'div.cover-edit-panel:not(.hide-panel)'
        ).get_by_role("button", name="Confirm")
        await confirm.click()
        await page.wait_for_timeout(1000)

    async def confirm_unfinished_checks(self, page):
        """Accept only the user's approved immediate-post copyright warning."""
        if self.publish_date != 0:
            # A scheduled request must never be changed into an immediate post.
            return False
        for frame in page.frames:
            titles = frame.get_by_text(re.compile(r"^继续发布[?？]$"))
            for index in range(await titles.count()):
                title = titles.nth(index)
                if not await title.is_visible():
                    continue
                # Studio modals may lack role=dialog. Start from the exact title
                # and use its nearest button-containing ancestor, not the page.
                modal = title.locator(
                    'xpath=ancestor::*[not(self::body) and not(self::html)]'
                    '[.//*[self::button or @role="button"]'
                    '[normalize-space(.)="立即发布"]][1]'
                )
                if not await modal.count() or not await modal.is_visible():
                    continue
                text = await modal.inner_text(timeout=1000)
                if not ("版权检查未完成" in text and "停止检查" in text):
                    continue
                confirm = modal.get_by_role("button", name="立即发布", exact=True)
                cancel = modal.get_by_role("button", name="取消", exact=True)
                if (await confirm.count() != 1 or await cancel.count() != 1
                        or not await cancel.is_visible()
                        or not await confirm.is_visible()
                        or not await confirm.is_enabled()):
                    continue
                await confirm.click(timeout=1000)
                tiktok_logger.info("TikTok 检查尚未完成，按用户设置点击立即发布，继续等待发布结果")
                return True
        return False

    async def wait_for_publish_result(self, page, timeout=300000):
        deadline = asyncio.get_running_loop().time() + timeout / 1000
        confirmed = False
        while asyncio.get_running_loop().time() < deadline:
            url = urlsplit(page.url)
            if (url.hostname == "www.tiktok.com"
                    and url.path.rstrip("/") == "/tiktokstudio/content"):
                return
            if not confirmed:
                confirmed = await self.confirm_unfinished_checks(page)
            # Do not click either submit button again while processing is slow.
            await asyncio.sleep(0.25)
        raise PlaywrightTimeoutError("TikTok 未确认发布成功，请检查平台内容列表；不要直接重复提交")

    async def click_publish(self, page):
        # Studio's first-use editor tour can cover the submit control.
        notice = page.get_by_role("button", name=re.compile(r"^(知道了|Got it)$", re.I))
        try:
            await notice.click(timeout=3000)
        except PlaywrightTimeoutError:
            pass
        publish_button = self.publish_button()
        await publish_button.click(timeout=60000)
        # Submit once; a slow confirmation must not trigger duplicate posts.
        await self.wait_for_publish_result(page)
        tiktok_logger.success("  [-] video published success")

    def publish_button(self):
        return self.locator_base.get_by_role(
            "button", name=re.compile(r"^(Post|Publish|发布|發佈)$", re.I)
        ).first

    async def detect_upload_status(self, page):
        deadline = asyncio.get_running_loop().time() + 1800
        while asyncio.get_running_loop().time() < deadline:
            try:
                publish_button = self.publish_button()
                if await publish_button.count() and await publish_button.is_visible() and await publish_button.is_enabled():
                    tiktok_logger.info("  [-]video uploaded.")
                    return
                else:
                    tiktok_logger.info("  [-] video uploading...")
                    await asyncio.sleep(2)
                    if await self.locator_base.locator('button[aria-label="Select file"]').count():
                        tiktok_logger.info("  [-] found some error while uploading now retry...")
                        await self.handle_upload_error(page)
            except:
                tiktok_logger.info("  [-] video uploading...")
                await asyncio.sleep(2)
        raise TimeoutError("TikTok video upload did not complete within 30 minutes")

    async def choose_base_locator(self, page):
        if await page.locator('iframe[data-tt="Upload_index_iframe"]').count():
            self.locator_base = page.frame_locator('iframe[data-tt="Upload_index_iframe"]')
        else:
            self.locator_base = page.locator(Tk_Locator.default)

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)
