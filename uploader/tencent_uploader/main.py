# -*- coding: utf-8 -*-
from datetime import datetime

from playwright.async_api import Playwright, async_playwright, expect, TimeoutError as PlaywrightTimeoutError
import os
import asyncio
import re
import time
from utils.publish_lifecycle import close_owned_browser

from conf import LOCAL_CHROME_PATH
from utils.base_social_media import set_init_script
from utils.browser_runtime import chromium_launch_options
from utils.files_times import get_absolute_path
from utils.log import tencent_logger

LAOLU_PRODUCT_ID = '10000436376366'
LAOLU_PRODUCT_NAME = '陆老师岳老师的视频创业课'
PRODUCT_TIMEOUT_MS = 15 * 60 * 1000
PRODUCT_CONFIRM = re.compile(r'^\s*(?:添加(?:\s*[（(]\s*1\s*[）)])?|确\s*[认定](?:\s*[（(]\s*1\s*[）)])?)\s*$')
PRODUCT_DIALOG_ACTION = re.compile(r'^\s*(?:添加(?:\s*[（(]\s*\d+\s*[）)])?|确\s*[认定](?:\s*[（(]\s*\d+\s*[）)])?)\s*$')
PRODUCT_DIALOGS = '[role="dialog"]:visible, .weui-desktop-dialog:visible, .weui-desktop-dialog__wrp:visible'

def format_str_for_short_title(origin_title: str) -> str:
    # 定义允许的特殊字符
    allowed_special_chars = "《》“”:+?%°"

    # 移除不允许的特殊字符
    filtered_chars = [char if char.isalnum() or char in allowed_special_chars else ' ' if char == ',' else '' for
                      char in origin_title]
    formatted_string = ''.join(filtered_chars)

    # 调整字符串长度
    if len(formatted_string) > 16:
        # 截断字符串
        formatted_string = formatted_string[:16]
    elif len(formatted_string) < 6:
        # 使用空格来填充字符串
        formatted_string += ' ' * (6 - len(formatted_string))

    return formatted_string


async def cookie_auth(account_file):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**chromium_launch_options(headless=True))
        context = await browser.new_context(storage_state=account_file)
        context = await set_init_script(context)
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://channels.weixin.qq.com/platform/post/create")
        try:
            await page.wait_for_selector('div.title-name:has-text("微信小店")', timeout=5000)  # 等待5秒
            tencent_logger.error("[+] 等待5秒 cookie 失效")
            return False
        except:
            tencent_logger.success("[+] cookie 有效")
            return True


async def get_tencent_cookie(account_file):
    async with async_playwright() as playwright:
        options = chromium_launch_options(headless=False, args=['--lang en-GB'])
        # Make sure to run headed.
        browser = await playwright.chromium.launch(**options)
        # Setup context however you like.
        context = await browser.new_context()  # Pass any options
        # Pause the page, and start recording manually.
        context = await set_init_script(context)
        page = await context.new_page()
        await page.goto("https://channels.weixin.qq.com")
        await page.pause()
        # 点击调试器的继续，保存cookie
        await context.storage_state(path=account_file)


async def weixin_setup(account_file, handle=False):
    account_file = get_absolute_path(account_file, "tencent_uploader")
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            # Todo alert message
            return False
        tencent_logger.info('[+] cookie文件不存在或已失效，即将自动打开浏览器，请扫码登录，登陆后会自动生成cookie文件')
        await get_tencent_cookie(account_file)
    return True


class TencentVideo(object):
    def __init__(self, title, file_path, tags, endpublishTime: str, account_file, category=None,enableTimer=False, *, account_name=''):
        self.title = title  # 视频标题
        self.file_path = file_path
        self.tags = tags
        self.endpublishTime = endpublishTime
        self.account_file = account_file
        self.category = category
        self.local_executable_path = LOCAL_CHROME_PATH
        self.enable_timer = enableTimer
        self.account_name = account_name

    @staticmethod
    def product_dialog(page, title):
        # Include the footer: some versions put it outside the inner dialog body.
        return page.locator(PRODUCT_DIALOGS).filter(
            has=page.get_by_text(title, exact=True)
        ).filter(has=page.get_by_text(PRODUCT_DIALOG_ACTION)).last

    @staticmethod
    async def confirm_product_dialog(dialog, timeout):
        # Text also covers custom div/a controls without an accessible button role.
        confirm = dialog.get_by_text(PRODUCT_CONFIRM).locator('visible=true')
        await expect(confirm).to_have_count(1, timeout=timeout)
        await expect(confirm).to_be_enabled(timeout=timeout)
        disabled = confirm.locator(
            "xpath=ancestor-or-self::*[@disabled or @aria-disabled='true' "
            "or contains(@class, 'disabled')]"
        )
        await expect(disabled).to_have_count(0, timeout=timeout)
        await confirm.click(timeout=timeout)

    async def confirm_product_timing(self, page, timeout):
        timing = self.product_dialog(page, '选择商品出现时机')
        deadline = time.monotonic() + timeout / 1000
        opened = False
        # The picker may open this automatically, or expose the edit link first.
        while not await timing.is_visible():
            remaining = int((deadline - time.monotonic()) * 1000)
            if remaining <= 0:
                raise RuntimeError('未出现商品时机确认窗口')
            edit = page.get_by_text('修改商品出现时机', exact=True).locator('visible=true')
            if not opened and await edit.count() == 1:
                try:
                    await edit.click(timeout=min(1000, remaining))
                    opened = True
                except PlaywrightTimeoutError:
                    # A delayed automatic dialog can cover the edit link.
                    pass
            await asyncio.sleep(0.1)
        await timing.get_by_text(re.compile(r'^\s*视频播放\s*5\s*秒后出现\s*$')).click(timeout=timeout)
        await self.confirm_product_dialog(timing, timeout)
        await timing.wait_for(state='hidden', timeout=timeout)

    def product_stage(self, stage):
        self._product_stage = stage
        tencent_logger.info('视频号商品步骤：{}', stage)

    async def add_required_product(self, page, timeout=PRODUCT_TIMEOUT_MS):
        """Attach the explicitly requested course only for 老陆 account names."""
        if '老陆' not in self.account_name:
            return
        self._product_stage = '打开商品入口'
        try:
            # One shared allowance, not a fresh 15 minutes for every action.
            await asyncio.wait_for(self._add_required_product(page, timeout), timeout=timeout / 1000)
        except Exception as exc:
            # Record the actual failed locator without logging cookies or locals.
            tencent_logger.error('视频号商品步骤失败 [{}] {}: {}',
                                 self._product_stage, type(exc).__name__, str(exc))
            raise RuntimeError(f'视频号商品步骤【{self._product_stage}】未完成，已停止发布；'
                               '详情见 logs/tencent.log') from exc

    async def _add_required_product(self, page, timeout):
        try:
            self.product_stage('打开商品入口')
            form = page.locator('div.form').filter(has=page.locator('div.input-editor'))
            # Product controls may use either an input placeholder or plain text.
            chooser = page.get_by_text('选择链接', exact=True).or_(page.get_by_placeholder('选择链接', exact=True))
            await chooser.locator('visible=true').click(timeout=timeout)
            await page.get_by_text('商品', exact=True).locator('visible=true').click(timeout=timeout)
            picker = page.get_by_text('选择需要添加的商品', exact=True).or_(
                page.get_by_placeholder('选择需要添加的商品', exact=True))
            await picker.locator('visible=true').click(timeout=timeout)
            self.product_stage('等待橱窗商品弹窗')
            dialog = self.product_dialog(page, '从橱窗添加商品')
            await dialog.wait_for(state='visible', timeout=timeout)
            await dialog.get_by_text('从橱窗添加商品', exact=True).click(timeout=timeout)
            self.product_stage('按商品编号筛选')
            search = dialog.get_by_placeholder('请输入商品名称/编码搜索', exact=True)
            await search.fill(LAOLU_PRODUCT_ID, timeout=timeout)
            await dialog.get_by_text('筛选', exact=True).click(timeout=timeout)
            self.product_stage('定位指定商品行')
            # The ID label and number may be separate DOM nodes. Match the
            # exact number, not a substring, and ignore hidden duplicate rows.
            identity = dialog.get_by_text(re.compile(
                r'^\s*(?:ID\s*[:：]?\s*)?' + LAOLU_PRODUCT_ID + r'\s*$'
            )).locator('visible=true')
            await expect(identity).to_have_count(1, timeout=timeout)
            self.product_stage('核对商品名称和选择控件')
            row = identity.locator(
                "xpath=ancestor::*[.//input[@type='radio' or @type='checkbox'] "
                "or .//*[@role='radio' or @role='checkbox']][1]"
            )
            await expect(row.get_by_text(LAOLU_PRODUCT_NAME, exact=True)).to_be_visible(timeout=timeout)
            self.product_stage('选中指定商品')
            control = row.locator('input[type="radio"], input[type="checkbox"], '
                                  '[role="radio"], [role="checkbox"]')
            await expect(control).to_have_count(1, timeout=timeout)
            # Do not toggle a previously selected checkbox off.
            if not await control.is_checked():
                if await control.is_visible():
                    await control.check(timeout=timeout)
                else:
                    await row.click(timeout=timeout)
            await expect(control).to_be_checked(timeout=timeout)
            self.product_stage('确认添加商品')
            await self.confirm_product_dialog(dialog, timeout)
            await dialog.wait_for(state='hidden', timeout=timeout)
            self.product_stage('确认商品出现时机')
            await self.confirm_product_timing(page, timeout)
            self.product_stage('核对发布表单中的商品')
            # A disappearing picker alone is not evidence of attachment.
            await expect(form.get_by_text(LAOLU_PRODUCT_NAME, exact=True)).to_be_visible(timeout=timeout)
            tencent_logger.info('已添加指定课程商品：' + LAOLU_PRODUCT_ID)
        except asyncio.CancelledError:
            # wait_for cancels on the shared deadline. Log the current stage.
            tencent_logger.error('视频号商品等待已到期或任务被取消，当前步骤：{}', self._product_stage)
            raise

    async def set_schedule_time_tencent(self, page, publish_date):
        label_element = page.locator("label").filter(has_text="定时").nth(1)
        await label_element.click()

        await page.click('input[placeholder="请选择发表时间"]')

        str_month = str(publish_date.month) if publish_date.month > 9 else "0" + str(publish_date.month)
        current_month = str_month + "月"
        # 获取当前的月份
        page_month = await page.inner_text('span.weui-desktop-picker__panel__label:has-text("月")')

        # 检查当前月份是否与目标月份相同
        if page_month != current_month:
            await page.click('button.weui-desktop-btn__icon__right')

        # 获取页面元素
        elements = await page.query_selector_all('table.weui-desktop-picker__table a')

        # 遍历元素并点击匹配的元素
        for element in elements:
            if 'weui-desktop-picker__disabled' in await element.evaluate('el => el.className'):
                continue
            text = await element.inner_text()
            if text.strip() == str(publish_date.day):
                await element.click()
                break

        # 输入小时部分（假设选择11小时）
        ##container-wrap > div.container-center > div > div > div.main-body-wrap.post-create > div.main-body > div > div.post-edit-wrap.material-edit-wrap > div.form > div.post-time-wrap > div:nth-child(2) > div.form-item-body > dl > dd > div > div.weui-desktop-picker__panel-fd > dl > dt > span > div > span > input
        await page.click('input[placeholder="请选择时间"]')
        await page.keyboard.press("Meta+A")
        await page.fill('input[placeholder="请选择时间"]', f'{publish_date.hour}')
        await asyncio.sleep(1)
        await page.keyboard.press("Enter")

        # 选择标题栏（令定时时间生效）
        await page.locator("div.input-editor").click()

    async def handle_upload_error(self, page):
        tencent_logger.info("视频出错了，重新上传中")
        await page.locator('div.media-status-content div.tag-inner:has-text("删除")').click()
        await page.get_by_role('button', name="删除", exact=True).click()
        file_input = page.locator('input[type="file"]')
        await file_input.set_input_files(self.file_path)

    async def upload(self, playwright: Playwright) -> None:
        # 使用 Chromium (这里使用系统内浏览器，用chromium 会造成h264错误
        browser = await playwright.chromium.launch(**chromium_launch_options(headless=False))
        context = None
        try:
            context = await browser.new_context(storage_state=f"{self.account_file}")
            context = await set_init_script(context)
            page = await context.new_page()
            await self.publish_page(page)
            await context.storage_state(path=f"{self.account_file}")
            tencent_logger.success('  [-]cookie更新完毕！')
        finally:
            await self.close_publish_browser(context, browser)

    async def close_publish_browser(self, context, browser, timeout=10):
        await close_owned_browser(context, browser, tencent_logger, timeout)

    async def publish_page(self, page):
        # 访问指定的 URL
        await page.goto("https://channels.weixin.qq.com/platform/post/create")
        tencent_logger.info(f'[+]正在上传-------{self.title}.mp4')
        # 等待页面跳转到指定的 URL，没进入，则自动等待到超时
        await page.wait_for_url("https://channels.weixin.qq.com/platform/post/create")
        # await page.wait_for_selector('input[type="file"]', timeout=10000)
        file_input = page.locator('input[type="file"]')
        await file_input.set_input_files(self.file_path)
        # 填充标题和话题
        await self.add_title_tags(page)
        # 合集功能
         # 位置选择
        await self.set_location(page)
        await self.add_collection(page)
        # 原创选择
        #await self.add_original(page)
        # 检测上传状态
        await self.detect_upload_status(page)
        await self.add_original(page)
        await self.add_mark(page)

        if self.enable_timer:
            publish_date = parse_publish_date(self.endpublishTime)
            await self.set_schedule_time_tencent(page, publish_date)
        # 添加短标题
        await self.add_short_title(page)

        await self.add_required_product(page)
        await self.click_publish(page)

    async def add_short_title(self, page):
        short_title_element = page.get_by_text("短标题", exact=True).locator("..").locator(
            "xpath=following-sibling::div").locator(
            'span input[type="text"]')
        if await short_title_element.count():
            short_title = format_str_for_short_title(self.title)
            await short_title_element.fill(short_title)
    async def set_location(self, page):
         location_elements = page.get_by_text("位置").locator("xpath=following-sibling::div").locator(
            '.common-option-list-wrap > div')

         if await location_elements.count() > 1:
            await page.get_by_text("位置").locator("xpath=following-sibling::div").click()
            await location_elements.first.click()

    async def click_publish(self, page):
        # Submit once; slow processing must not trigger duplicate publication.
        await page.locator('div.form-btns button:has-text("发表")').click(timeout=60000)
        try:
            await page.wait_for_url(re.compile(
                r'^https://channels\.weixin\.qq\.com/platform/post/list(?:[?#].*)?$'
            ), timeout=PRODUCT_TIMEOUT_MS, wait_until='domcontentloaded')
        except PlaywrightTimeoutError as exc:
            raise RuntimeError('视频号未确认发表结果，请先检查作品列表，勿直接重复发布') from exc
        tencent_logger.success("  [-]视频发布成功")

    async def detect_upload_status(self, page):
        while True:
            # 匹配删除按钮，代表视频上传完毕，如果不存在，代表视频正在上传，则等待
            try:
                # 匹配删除按钮，代表视频上传完毕
                if "weui-desktop-btn_disabled" not in await page.get_by_role("button", name="发表").get_attribute(
                        'class'):
                    tencent_logger.info("  [-]视频上传完毕")
                    break
                else:
                    tencent_logger.info("  [-] 正在上传视频中...")
                    await asyncio.sleep(2)
                    # 出错了视频出错
                    if await page.locator('div.status-msg.error').count() and await page.locator(
                            'div.media-status-content div.tag-inner:has-text("删除")').count():
                        tencent_logger.error("  [-] 发现上传出错了...准备重试")
                        await self.handle_upload_error(page)
            except:
                tencent_logger.info("  [-] 正在上传视频中...")
                await asyncio.sleep(2)

    async def add_title_tags(self, page):
        await page.locator("div.input-editor").click()
        await page.keyboard.type(self.title)
        await page.keyboard.press("Enter")
        for index, tag in enumerate(self.tags, start=1):
            await page.keyboard.type("#" + tag)
            await page.keyboard.press("Space")
        await page.keyboard.type("#喀理系统")
        await page.keyboard.press("Space")
        await page.keyboard.type("@岳同学AI")
        await page.keyboard.press("Space")
        tencent_logger.info(f"成功添加hashtag: {len(self.tags) + 1}，并添加 @岳同学AI")

    async def add_collection(self, page):
        collection_elements = page.get_by_text("添加到合集").locator("xpath=following-sibling::div").locator(
            '.option-list-wrap > div')
        if await collection_elements.count() > 1:
            await page.get_by_text("添加到合集").locator("xpath=following-sibling::div").click()
            await collection_elements.first.click()

    async def add_original(self, page):
        if await page.get_by_label("声明后，作品将展示原创标记，有机会获得广告收入").count():
            await page.get_by_label("声明后，作品将展示原创标记，有机会获得广告收入").check()
        # 检查 "我已阅读并同意 《视频号原创声明使用条款》" 元素是否存在
        #container-wrap > div.container-center > div > div > div.main-body-wrap.post-create > div.main-body > div > div.post-edit-wrap.material-edit-wrap > div.form > div:nth-child(8) > div.declare-original-dialog > div.weui-desktop-dialog__wrp > div > div.weui-desktop-dialog__bd > div > div.original-proto-wrapper

        # 处理新的原创声明对话框结构（用户提供的HTML）
        # 使用更具体的选择器定位对话框内的元素，避免严格模式违规
        dialog_wrapper = page.locator('div.declare-original-dialog div.original-proto-wrapper').first
        original_proto_wrapper = await dialog_wrapper.is_visible()
        if original_proto_wrapper:
            # 点击复选框
            checkbox_locator = dialog_wrapper.locator('input.ant-checkbox-input').first
            if await checkbox_locator.count():
                await checkbox_locator.click()
                await page.wait_for_timeout(500)  # 等待复选框状态更新

            # 点击声明原创按钮
            declare_button = page.locator('div.weui-desktop-dialog__ft button:has-text("声明原创")').first
            if await declare_button.count():
                await declare_button.click()

    async def add_mark(self, page):
        """选择视频号新版发布页的第二个内容标记项。"""
        mark_selector = page.locator("div.mark-tag-select")
        if not await mark_selector.count():
            return
        await mark_selector.first.click()
        await page.wait_for_timeout(1000)
        options = page.locator("div.mark-tag-options .mark-tag-option")
        if await options.count() > 1:
            await options.nth(1).click()
            await page.wait_for_timeout(1000)
        else:
            tencent_logger.warning("  [-] 未找到视频号内容标记的第二个选项，已跳过")

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)
def parse_publish_date(publish_date_str: str) -> datetime:
    """解析 'YYYY年M月D日 HH:MM:SS' 返回 datetime 对象"""
    publish_date_str = f'{publish_date_str}'.replace('T', ' ').replace('.000+00:00', '').strip()
    print(publish_date_str)
    return datetime.strptime(publish_date_str, '%Y-%m-%d %H:%M:%S')

def format_publish_date_str(publish_date_str: str) -> str:
    """将 'YYYY年M月D日 HH:MM' 转为 'YYYY-MM-DD HH:MM:SS' 字符串"""
    dt = datetime.strptime(publish_date_str.strip(), '%Y年%m月%d日 %H:%M')
    return dt.strftime('%Y-%m-%d %H:%M:%S')
