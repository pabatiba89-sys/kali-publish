# -*- coding: utf-8 -*-
from datetime import datetime

from playwright.async_api import Playwright, async_playwright, Page, TimeoutError as PlaywrightTimeoutError
import os
import asyncio

from conf import BASE_DIR, LOCAL_CHROME_PATH
from utils.base_social_media import set_init_script
from utils.browser_runtime import chromium_launch_options
from utils.log import xiaohongshu_logger


async def cookie_auth(account_file):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**chromium_launch_options(headless=True))
        context = await browser.new_context(storage_state=account_file)
        context = await set_init_script(context)
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://creator.xiaohongshu.com/creator-micro/content/upload")
        try:
            await page.wait_for_url("https://creator.xiaohongshu.com/creator-micro/content/upload", timeout=5000)
        except:
            print("[+] 等待5秒 cookie 失效")
            await context.close()
            await browser.close()
            return False
        # 2024.06.17 抖音创作者中心改版
        if await page.get_by_text('手机号登录').count() or await page.get_by_text('扫码登录').count():
            print("[+] 等待5秒 cookie 失效")
            return False
        else:
            print("[+] cookie 有效")
            return True


async def xiaohongshu_setup(account_file, handle=False):
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            # Todo alert message
            return False
        xiaohongshu_logger.info('[+] cookie文件不存在或已失效，即将自动打开浏览器，请扫码登录，登陆后会自动生成cookie文件')
        await xiaohongshu_cookie_gen(account_file)
    return True


async def xiaohongshu_cookie_gen(account_file):
    async with async_playwright() as playwright:
        options = chromium_launch_options(headless=False, args=['--lang en-GB'])
        # Make sure to run headed.
        browser = await playwright.chromium.launch(**options)
        # Setup context however you like.
        context = await browser.new_context()  # Pass any options
        context = await set_init_script(context)
        # Pause the page, and start recording manually.
        page = await context.new_page()
        await page.goto("https://creator.xiaohongshu.com/")
        await page.pause()
        # 点击调试器的继续，保存cookie
        await context.storage_state(path=account_file)


class XiaoHongShuVideo(object):
    def __init__(self, title, file_path, tags, publish_date: datetime, account_file,enableTimer=False, thumbnail_path=None):
        self.title = title  # 视频标题
        self.file_path = file_path
        self.tags = tags
        self.publish_date = publish_date
        self.account_file = account_file
        self.date_format = '%Y年%m月%d日 %H:%M'
        self.local_executable_path = LOCAL_CHROME_PATH
        self.thumbnail_path = thumbnail_path
        self.enableTimer = enableTimer

    async def set_schedule_time_xiaohongshu(self, page, publish_date):
        print("  [-] 正在设置定时发布时间...")
        print(f"publish_date: {publish_date}")

        # 使用文本内容定位元素
        # element = await page.wait_for_selector(
        #     'label:has-text("定时发布")',
        #     timeout=5000  # 5秒超时时间
        # )
        # await element.click()

        # # 选择包含特定文本内容的 label 元素
        # await page.locator('label:has-text("定时发布")').click()
##p div.post-time-switch-container > div > div > div.custom-switch-switch > div > div > div > span
        await page.locator('div.post-time-switch-container').locator('span.d-switch-simulator').click()
        xiaohongshu_logger.info(f'shifouzhaodao')
        await page.locator('div.date-picker-container').click()

        publish_date_hour = publish_date.strftime("%Y-%m-%d %H:%M")
        print(f"publish_date_hour: {publish_date_hour}")


        await page.locator('div.date-picker-container').locator('div.d-datepicker-input-filter').locator('input.d-text').fill(f"{publish_date_hour}")
        await page.keyboard.press("Tab")

        await asyncio.sleep(0.5)

    async def handle_upload_error(self, page):
        xiaohongshu_logger.info('视频出错了，重新上传中')
        await page.locator('div.progress-div [class^="upload-btn-input"]').set_input_files(self.file_path)

    async def wait_video_ready(self, page, timeout=600000):
        # The file input may be hidden after upload; wait for the actual ready marker.
        await page.locator('.video-plugin-title-action').filter(
            has_text='重新上传'
        ).first.wait_for(state='visible', timeout=timeout)

    async def submit_and_confirm(self, page, timeout=60000):
        editor = page.locator('.ProseMirror').first
        if await editor.count():
            await editor.press('Tab')  # Leave the topic suggestion dropdown.
        if await page.locator('xhs-publish-btn').count():
            await self.click_shadow_publish(page, timeout)
        else:
            await page.get_by_text('发布', exact=True).locator('visible=true').first.click(timeout=timeout)
        try:
            await page.wait_for_url('**/publish/success**', timeout=timeout)
        except PlaywrightTimeoutError as exc:
            raise RuntimeError('小红书已点击发布，但未确认成功；请检查页面提示，不要重复提交') from exc

    async def click_shadow_publish(self, page, timeout):
        # The new footer keeps its buttons in a closed shadow root. Read that
        # component via CDP, respect its real disabled state, then use a normal
        # pointer click on the publish button (never dispatch a synthetic submit).
        def attributes(node):
            items = node.get('attributes', [])
            return dict(zip(items[::2], items[1::2]))

        def nodes(node):
            yield node
            for child in node.get('children', []) + node.get('shadowRoots', []):
                yield from nodes(child)

        cdp = await page.context.new_cdp_session(page)
        deadline = asyncio.get_running_loop().time() + timeout / 1000
        try:
            while asyncio.get_running_loop().time() < deadline:
                root = await cdp.send('DOM.getDocument')
                host = await cdp.send('DOM.querySelector', {
                    'nodeId': root['root']['nodeId'], 'selector': 'xhs-publish-btn',
                })
                if host['nodeId']:
                    tree = (await cdp.send('DOM.describeNode', {
                        'nodeId': host['nodeId'], 'depth': -1, 'pierce': True,
                    }))['node']
                    label = attributes(tree).get('submit-text', '发布')
                    for button in nodes(tree):
                        if button.get('nodeName') != 'BUTTON':
                            continue
                        text = ''.join(n.get('nodeValue', '') for n in nodes(button)).strip()
                        attrs = attributes(button)
                        if text != label or 'disabled' in attrs or attrs.get('aria-disabled') == 'true' or attrs.get('aria-busy') == 'true':
                            continue
                        target = {'backendNodeId': button['backendNodeId']}
                        await cdp.send('DOM.scrollIntoViewIfNeeded', target)
                        box = (await cdp.send('DOM.getBoxModel', target))['model']
                        if box['width'] > 0 and box['height'] > 0:
                            quad = box['border']
                            await page.mouse.click(sum(quad[::2]) / 4, sum(quad[1::2]) / 4)
                            return
                await asyncio.sleep(0.25)
        finally:
            await cdp.detach()
        raise TimeoutError('小红书发布按钮不可用，请检查上传处理进度、封面或必填提示')

    async def upload(self, playwright: Playwright) -> None:
        # 使用 Chromium 浏览器启动一个浏览器实例
        browser = await playwright.chromium.launch(**chromium_launch_options(headless=False))
        # 创建一个浏览器上下文，使用指定的 cookie 文件
        context = await browser.new_context(
            viewport={"width": 1600, "height": 900},
            storage_state=f"{self.account_file}"
        )
        context = await set_init_script(context)

        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://creator.xiaohongshu.com/publish/publish?from=homepage&target=video")
        xiaohongshu_logger.info(f'[+]正在上传-------{self.title}.mp4')
        # 等待页面跳转到指定的 URL，没进入，则自动等待到超时
        xiaohongshu_logger.info(f'[-] 正在打开主页...')
        await page.wait_for_url("https://creator.xiaohongshu.com/publish/publish?from=homepage&target=video")
        # 点击 "上传视频" 按钮
        await page.locator("div[class^='upload-content'] input[class='upload-input']").set_input_files(self.file_path)

        await self.wait_video_ready(page)
        xiaohongshu_logger.info("[+] 检测到上传成功标识!")
        # 填充标题和话题
        # 检查是否存在包含输入框的元素
        # 这里为了避免页面变化，故使用相对位置定位：作品标题父级右侧第一个元素的input子元素
        await asyncio.sleep(1)
        xiaohongshu_logger.info(f'  [-] 正在填充标题和话题...')
        #//*[@id="publish-container"]/div[2]/div[1]/div/div[1]/div[3]/div/div[1]/div[1]/div[1]/div/input
        ##publish-container > div.publish-page-container > div.style-override-container.red-theme-override-container > div > div.publish-page-content > div.publish-page-content-base > div > div.flex > div.input > div.d-input-wrapper.d-inline-block.c-input_inner > div > input
        #document.querySelector("#publish-container > div.publish-page-container > div.style-override-container.red-theme-override-container > div > div.publish-page-content > div.publish-page-content-base > div > div.flex > div.input > div.d-input-wrapper.d-inline-block.c-input_inner > div > input")
        title_container = page.locator('div.publish-page-content-base').locator('input.d-text')
        if await title_container.count():
            await title_container.fill(self.title[:20])
        else:
            ##publish-container > div.publish-page-container > div.style-override-container.red-theme-override-container > div > div.publish-page-content > div.publish-page-content-base > div > div.editor-container > div.editor-content > div > div
            titlecontainer = page.locator("div.editor-content.div.div")
            await titlecontainer.click()
            await page.keyboard.press("Backspace")
            await page.keyboard.press("Meta+A")
            await page.keyboard.press("Delete")
            await page.keyboard.type(self.title)
            await page.keyboard.press("Enter")
        css_selector = ".ProseMirror" # 不能加上 .ql-blank 属性，这样只能获取第一次非空状态
        for index, tag in enumerate(self.tags[:10], start=1):
            await page.type(css_selector, "#" + tag)
            await asyncio.sleep(0.5)
            await page.press(css_selector, "Enter")
            await page.press(css_selector, "Space")

        xiaohongshu_logger.info(f'总共添加{len(self.tags)}个话题')
        if self.enableTimer:
            await self.set_schedule_time_xiaohongshu(page, self.publish_date)

        try:
            await self.submit_and_confirm(page)
        except Exception:
            try:
                await page.screenshot(path=str(BASE_DIR / "logs/xiaohongshu-publish-failure.png"), full_page=True)
            finally:
                await context.close()
                await browser.close()
            raise
        xiaohongshu_logger.success("  [-]视频发布成功")

        await context.storage_state(path=self.account_file)  # 保存cookie
        xiaohongshu_logger.success('  [-]cookie更新完毕！')
        await asyncio.sleep(2)  # 这里延迟是为了方便眼睛直观的观看
        # 关闭浏览器上下文和浏览器实例
        await context.close()
        await browser.close()

    async def set_thumbnail(self, page: Page, thumbnail_path: str):
        if thumbnail_path:
            await page.click('text="选择封面"')
            await page.wait_for_selector("div.semi-modal-content:visible")
            await page.click('text="设置竖封面"')
            await page.wait_for_timeout(2000)  # 等待2秒
            # 定位到上传区域并点击
            await page.locator("div[class^='semi-upload upload'] >> input.semi-upload-hidden-input").set_input_files(thumbnail_path)
            await page.wait_for_timeout(2000)  # 等待2秒
            await page.locator("div[class^='extractFooter'] button:visible:has-text('完成')").click()
            # finish_confirm_element = page.locator("div[class^='confirmBtn'] >> div:has-text('完成')")
            # if await finish_confirm_element.count():
            #     await finish_confirm_element.click()
            # await page.locator("div[class^='footer'] button:has-text('完成')").click()

    async def set_location(self, page: Page, location: str = "青岛市"):
        print(f"开始设置位置: {location}")

        # 点击地点输入框
        print("等待地点输入框加载...")
        loc_ele = await page.wait_for_selector('div.d-text.d-select-placeholder.d-text-ellipsis.d-text-nowrap')
        print(f"已定位到地点输入框: {loc_ele}")
        await loc_ele.click()
        print("点击地点输入框完成")

        # 输入位置名称
        print(f"等待1秒后输入位置名称: {location}")
        await page.wait_for_timeout(1000)
        await page.keyboard.type(location)
        print(f"位置名称输入完成: {location}")

        # 等待下拉列表加载
        print("等待下拉列表加载...")
        dropdown_selector = 'div.d-popover.d-popover-default.d-dropdown.--size-min-width-large'
        await page.wait_for_timeout(60000)
        try:
            await page.wait_for_selector(dropdown_selector, timeout=60000)
            print("下拉列表已加载")
        except:
            print("下拉列表未按预期显示，可能结构已变化")

        # 增加等待时间以确保内容加载完成
        print("额外等待1秒确保内容渲染完成...")
        await page.wait_for_timeout(1000)

        # 尝试更灵活的XPath选择器
        print("尝试使用更灵活的XPath选择器...")
        flexible_xpath = (
            f'//div[contains(@class, "d-popover") and contains(@class, "d-dropdown")]'
            f'//div[contains(@class, "d-options-wrapper")]'
            f'//div[contains(@class, "d-grid") and contains(@class, "d-options")]'
            f'//div[contains(@class, "name") and text()="{location}"]'
        )
        await page.wait_for_timeout(60000)

        # 尝试定位元素
        print(f"尝试定位包含'{location}'的选项...")
        try:
            # 先尝试使用更灵活的选择器
            location_option = await page.wait_for_selector(
                flexible_xpath,
                timeout=60000
            )

            if location_option:
                print(f"使用灵活选择器定位成功: {location_option}")
            else:
                # 如果灵活选择器失败，再尝试原选择器
                print("灵活选择器未找到元素，尝试原始选择器...")
                location_option = await page.wait_for_selector(
                    f'//div[contains(@class, "d-popover") and contains(@class, "d-dropdown")]'
                    f'//div[contains(@class, "d-options-wrapper")]'
                    f'//div[contains(@class, "d-grid") and contains(@class, "d-options")]'
                    f'/div[1]//div[contains(@class, "name") and text()="{location}"]',
                    timeout=2000
                )

            # 滚动到元素并点击
            print("滚动到目标选项...")
            await location_option.scroll_into_view_if_needed()
            print("元素已滚动到视图内")

            # 增加元素可见性检查
            is_visible = await location_option.is_visible()
            print(f"目标选项是否可见: {is_visible}")

            # 点击元素
            print("准备点击目标选项...")
            await location_option.click()
            print(f"成功选择位置: {location}")
            return True

        except Exception as e:
            print(f"定位位置失败: {e}")

            # 打印更多调试信息
            print("尝试获取下拉列表中的所有选项...")
            try:
                all_options = await page.query_selector_all(
                    '//div[contains(@class, "d-popover") and contains(@class, "d-dropdown")]'
                    '//div[contains(@class, "d-options-wrapper")]'
                    '//div[contains(@class, "d-grid") and contains(@class, "d-options")]'
                    '/div'
                )
                print(f"找到 {len(all_options)} 个选项")

                # 打印前3个选项的文本内容
                for i, option in enumerate(all_options[:3]):
                    option_text = await option.inner_text()
                    print(f"选项 {i+1}: {option_text.strip()[:50]}...")

            except Exception as e:
                print(f"获取选项列表失败: {e}")

            # 截图保存（取消注释使用）
            # await page.screenshot(path=f"location_error_{location}.png")
            return False

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)
