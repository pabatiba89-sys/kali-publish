"""Network-isolated regression fixtures for TikTok's final confirmation."""
import unittest
from datetime import datetime

from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright

from uploader.tk_uploader.main import TiktokVideo
from utils.browser_runtime import chromium_launch_options


WARNING = """<section id="warning">
  <h2>继续发布?</h2>
  <p>版权检查未完成。现在发布你的视频将会停止检查。</p>
  <p>我们仍在检查你的视频是否存在潜在问题。检查尚未完成，仍要发布？</p>
  <button>取消</button>
  <button id="confirm" onclick="window.confirms++">立即发布</button>
</section>"""


class TikTokPublishTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runtime = await async_playwright().start()
        self.browser = await self.runtime.chromium.launch(**chromium_launch_options(True))
        self.page = await self.browser.new_page()
        # Every request is fulfilled locally, including the apparent Studio URL.
        await self.page.route("**/*", lambda route: route.fulfill(body="", content_type="text/html"))
        await self.page.goto("https://www.tiktok.com/tiktokstudio/upload")
        self.uploader = TiktokVideo("title", "unused", [], 0, "unused")
        self.uploader.locator_base = self.page.locator("body")

    async def asyncTearDown(self):
        await self.browser.close()
        await self.runtime.stop()

    async def warning(self, html=WARNING):
        await self.page.set_content('<script>window.confirms=0;window.posts=0</script>' + html)

    async def test_delayed_warning_and_result_submit_both_buttons_once(self):
        await self.warning(WARNING.replace('id="warning"', 'id="warning" hidden') + """
            <button onclick="this.remove()">知道了</button>
            <button onclick="window.posts++;setTimeout(()=>document.querySelector('#warning').hidden=false,100)">发布</button>""")
        await self.page.locator('#confirm').evaluate("""button => button.addEventListener('click', () => {
            setTimeout(()=>history.pushState({}, '', '/tiktokstudio/content?from=upload'), 900);
        })""")
        await self.uploader.click_publish(self.page)
        self.assertEqual(await self.page.evaluate('window.posts'), 1)
        self.assertEqual(await self.page.evaluate('window.confirms'), 1)

    async def test_confirmation_alone_is_not_success_or_retried(self):
        await self.warning()
        with self.assertRaises(PlaywrightTimeoutError):
            await self.uploader.wait_for_publish_result(self.page, timeout=800)
        self.assertEqual(await self.page.evaluate('window.confirms'), 1)

    async def test_disappeared_warning_is_not_success(self):
        await self.warning()
        await self.page.locator('#confirm').evaluate("button=>button.addEventListener('click',()=>document.querySelector('#warning').remove())")
        with self.assertRaises(PlaywrightTimeoutError):
            await self.uploader.wait_for_publish_result(self.page, timeout=500)
        self.assertEqual(await self.page.evaluate('window.confirms'), 1)

    async def test_unrelated_warning_is_not_accepted(self):
        await self.warning(WARNING.replace("版权检查未完成。现在发布你的视频将会停止检查。", "检测到版权违规，请先处理。"))
        self.assertFalse(await self.uploader.confirm_unfinished_checks(self.page))
        self.assertEqual(await self.page.evaluate('window.confirms'), 0)

    async def test_different_title_is_not_accepted(self):
        await self.warning(WARNING.replace("继续发布?", "确认其他操作?"))
        self.assertFalse(await self.uploader.confirm_unfinished_checks(self.page))
        self.assertEqual(await self.page.evaluate('window.confirms'), 0)

    async def test_hidden_warning_is_not_accepted(self):
        await self.warning(WARNING.replace('id="warning"', 'id="warning" hidden'))
        self.assertFalse(await self.uploader.confirm_unfinished_checks(self.page))
        self.assertEqual(await self.page.evaluate('window.confirms'), 0)

    async def test_disabled_confirmation_is_not_clicked(self):
        await self.warning(WARNING.replace('id="confirm"', 'id="confirm" disabled'))
        self.assertFalse(await self.uploader.confirm_unfinished_checks(self.page))
        self.assertEqual(await self.page.evaluate('window.confirms'), 0)

    async def test_scheduled_request_never_clicks_immediate(self):
        await self.warning()
        self.uploader.publish_date = datetime(2030, 1, 1)
        self.assertFalse(await self.uploader.confirm_unfinished_checks(self.page))
        self.assertEqual(await self.page.evaluate('window.confirms'), 0)

    async def test_warning_inside_iframe(self):
        await self.page.set_content('<iframe></iframe>')
        frame = self.page.frames[1]
        await frame.set_content('<script>window.confirms=0</script>' + WARNING)
        self.assertTrue(await self.uploader.confirm_unfinished_checks(self.page))
        self.assertEqual(await frame.evaluate('window.confirms'), 1)

    async def test_top_level_warning_with_iframe_uploader(self):
        await self.warning(WARNING + '<iframe></iframe>')
        self.uploader.locator_base = self.page.frames[1].locator('body')
        self.assertTrue(await self.uploader.confirm_unfinished_checks(self.page))
        self.assertEqual(await self.page.evaluate('window.confirms'), 1)

    async def test_success_without_warning(self):
        await self.warning('<button onclick="this.remove()">知道了</button><button onclick="window.posts++;history.pushState({}, \'\', \'/tiktokstudio/content\')">发布</button>')
        await self.uploader.click_publish(self.page)
        self.assertEqual(await self.page.evaluate('window.posts'), 1)
        self.assertEqual(await self.page.evaluate('window.confirms'), 0)

    async def test_success_url_in_query_is_not_success(self):
        await self.page.evaluate("history.pushState({}, '', '/login?next=/tiktokstudio/content')")
        with self.assertRaises(PlaywrightTimeoutError):
            await self.uploader.wait_for_publish_result(self.page, timeout=300)


if __name__ == '__main__':
    unittest.main()
