"""Offline browser fixtures for re-login inside an existing publishing window."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from playwright.async_api import async_playwright

from uploader.alipay_uploader.main import AlipayVideo, ALIPAY_PORTAL_HOME
from utils.browser_runtime import chromium_launch_options


class AlipayPublishLoginTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runtime = await async_playwright().start()
        self.browser = await self.runtime.chromium.launch(**chromium_launch_options(True))
        self.page = await self.browser.new_page()
        self.uploader = AlipayVideo('title', 'unused', [], 'unused')
        self.portal = '''<iframe title="login" srcdoc="扫码登录"></iframe>
            <script>setTimeout(()=>document.querySelector('iframe').hidden=true,700)</script>'''

        async def fixture(route):
            if '/portal/' in route.request.url:
                html = self.portal
            elif '/life-account/' in route.request.url:
                html = '<a href="/content-creation/publish/short-video">发布视频</a>'
            else:
                html = '<input type="file" accept="video/*">'
            await route.fulfill(body=html, content_type='text/html; charset=utf-8')
        await self.page.route('**/*', fixture)

    async def asyncTearDown(self):
        await self.browser.close()
        await self.runtime.stop()

    async def test_hidden_login_iframe_continues_to_upload_in_same_page(self):
        with patch('uploader.alipay_uploader.main.alipay_cookie_gen', AsyncMock()) as standalone:
            await self.uploader.login_for_publish(self.page, timeout=10)
            self.assertEqual(self.page.url, ALIPAY_PORTAL_HOME)
            self.assertFalse(self.page.is_closed())
            # Some portal versions hide rather than remove the login iframe.
            self.assertEqual(await self.page.locator('iframe[title="login"]').count(), 1)
            await self.uploader.open_upload_page(self.page)
            self.assertIn('/content-creation/publish/short-video', self.page.url)
            self.assertEqual(await self.page.locator('input[type=file]').count(), 1)
            self.assertEqual(len(self.page.context.pages), 1)
            self.assertFalse(self.page.is_closed())
        standalone.assert_not_awaited()

    async def test_portal_url_without_login_transition_is_not_success(self):
        self.portal = '<div>加载中</div>'
        with self.assertRaisesRegex(RuntimeError, '登录未完成'):
            await self.uploader.login_for_publish(self.page, timeout=0.3)
        self.assertFalse(self.page.is_closed())

    async def test_visible_login_iframe_does_not_complete(self):
        self.portal = '<iframe title="login" srcdoc="扫码登录"></iframe>'
        with self.assertRaisesRegex(RuntimeError, '登录未完成'):
            await self.uploader.login_for_publish(self.page, timeout=0.3)

    async def test_already_authenticated_portal_can_continue(self):
        self.portal = '<a href="/content-creation/publish/short-video">发布视频</a>'
        await self.uploader.login_for_publish(self.page, timeout=5)
        self.assertFalse(self.page.is_closed())

    async def test_closed_publish_login_page_is_cancelled(self):
        page = SimpleNamespace(goto=AsyncMock(), is_closed=lambda: True)
        with self.assertRaisesRegex(RuntimeError, '窗口已关闭'):
            await self.uploader.login_for_publish(page, timeout=5)


if __name__ == '__main__':
    unittest.main()
