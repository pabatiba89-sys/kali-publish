# -*- coding: utf-8 -*-
import re
from datetime import datetime

from playwright.async_api import Playwright, async_playwright
import os
import asyncio
from uploader.tk_uploader.tk_config import Tk_Locator
from utils.base_social_media import set_init_script
from utils.browser_runtime import chromium_launch_options
from utils.files_times import get_absolute_path
from utils.log import tiktok_logger
from conf import LOCAL_CHROME_HEADLESS


async def cookie_auth(account_file):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            **chromium_launch_options(headless=LOCAL_CHROME_HEADLESS)
        )
        context = await browser.new_context(storage_state=account_file)
        context = await set_init_script(context)
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://www.tiktok.com/tiktokstudio/upload?lang=en")
        await page.wait_for_load_state('networkidle')
        try:
            # 选择所有的 select 元素
            select_elements = await page.query_selector_all('select')
            for element in select_elements:
                class_name = await element.get_attribute('class')
                # 使用正则表达式匹配特定模式的 class 名称
                if re.match(r'tiktok-.*-SelectFormContainer.*', class_name):
                    tiktok_logger.error("[+] cookie expired")
                    return False
            tiktok_logger.success("[+] cookie valid")
            return True
        except:
            tiktok_logger.success("[+] cookie valid")
            return True


async def tiktok_setup(account_file, handle=False):
    account_file = get_absolute_path(account_file, "tk_uploader")
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            return False
        tiktok_logger.info('[+] cookie file is not existed or expired. Now open the browser auto. Please login with your way(gmail phone, whatever, the cookie file will generated after login')
        await get_tiktok_cookie(account_file)
    return True


async def get_tiktok_cookie(account_file):
    async with async_playwright() as playwright:
        options = chromium_launch_options(
            headless=LOCAL_CHROME_HEADLESS,
            args=['--lang en-GB'],
        )
        # Make sure to run headed.
        browser = await playwright.chromium.launch(**options)
        # Setup context however you like.
        context = await browser.new_context()  # Pass any options
        context = await set_init_script(context)
        # Pause the page, and start recording manually.
        page = await context.new_page()
        await page.goto("https://www.tiktok.com/login?lang=en")
        await page.pause()
        # 点击调试器的继续，保存cookie
        await context.storage_state(path=account_file)


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
        browser = await playwright.chromium.launch(
            **chromium_launch_options(headless=self.headless)
        )
        context = await browser.new_context(storage_state=f"{self.account_file}")
        context = await set_init_script(context)
        page = await context.new_page()

        await page.goto("https://www.tiktok.com/tiktokstudio/upload?lang=en")
        tiktok_logger.info(f'[+]Uploading-------{self.title}.mp4')

        try:
            await page.wait_for_selector('iframe[data-tt="Upload_index_iframe"], div.upload-container', timeout=10000)
            tiktok_logger.info("Either iframe or div appeared.")
        except Exception as e:
            tiktok_logger.error("Neither iframe nor div appeared within the timeout.")

        await self.choose_base_locator(page)

        upload_button = self.locator_base.locator(
            'button:has-text("Select video"):visible')
        await upload_button.wait_for(state='visible')  # 确保按钮可见

        async with page.expect_file_chooser() as fc_info:
            await upload_button.click()
        file_chooser = await fc_info.value
        await file_chooser.set_files(self.file_path)

        await self.add_title_tags(page)
        # detact upload status
        await self.detect_upload_status(page)
        if self.thumbnail_path:
            await self.upload_thumbnail(page)
        if self.publish_date != 0:
            await self.set_schedule_time(page, self.publish_date)

        await self.click_publish(page)

        await context.storage_state(path=f"{self.account_file}")  # save cookie
        tiktok_logger.info('  [-] update cookie！')
        await asyncio.sleep(2)  # close delay for look the video status
        # close all
        await context.close()
        await browser.close()

    async def add_title_tags(self, page):

        editor_locator = self.locator_base.locator('div.public-DraftEditor-content')
        await editor_locator.click()

        await page.keyboard.press("End")

        await page.keyboard.press("Control+A")

        await page.keyboard.press("Delete")

        await page.keyboard.press("End")

        await page.wait_for_timeout(1000)  # 等待1秒

        await page.keyboard.insert_text(self.caption)
        await page.wait_for_timeout(1000)  # 等待1秒
        await page.keyboard.press("End")

        await page.keyboard.press("Enter")

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

    async def click_publish(self, page):
        deadline = asyncio.get_running_loop().time() + 300
        while asyncio.get_running_loop().time() < deadline:
            try:
                publish_button = self.locator_base.locator(
                    'div.button-group > button:has-text("Post"), div.btn-post button'
                ).first
                await publish_button.wait_for(state="visible", timeout=10000)
                if await publish_button.get_attribute("disabled") is None:
                    await publish_button.click()
                await page.wait_for_url("**/tiktokstudio/content**", timeout=5000)
                tiktok_logger.success("  [-] video published success")
                return
            except Exception as e:
                tiktok_logger.info(f"  [-] video publishing: {type(e).__name__}")
                await asyncio.sleep(1)
        raise TimeoutError("TikTok did not confirm publication within 5 minutes")

    async def detect_upload_status(self, page):
        deadline = asyncio.get_running_loop().time() + 1800
        while asyncio.get_running_loop().time() < deadline:
            try:
                publish_button = self.locator_base.locator(
                    'div.button-group > button:has-text("Post"), div.btn-post > button'
                ).first
                if await publish_button.count() and await publish_button.get_attribute("disabled") is None:
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
