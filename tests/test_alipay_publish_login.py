"""Offline browser fixtures for re-login inside an existing publishing window."""
import unittest
import inspect
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

    async def test_temporary_hidden_login_frame_is_not_login_success(self):
        self.portal = '''<iframe title="login" srcdoc="扫码登录"></iframe>
          <script>
            setTimeout(()=>document.querySelector('iframe').hidden=true,100);
            setTimeout(()=>document.querySelector('iframe').hidden=false,600);
          </script>'''
        with self.assertRaisesRegex(RuntimeError, '登录未完成'):
            await self.uploader.login_for_publish(self.page, timeout=1.2)
        self.assertFalse(self.page.is_closed())

    async def test_upload_page_recovers_login_redirect_in_same_window(self):
        visits = []

        async def redirected_fixture(route):
            path = route.request.url
            visits.append(path)
            if '/life-account/' in path and len(visits) == 1:
                html = '''<script>location.href='/page/portal/home'</script>'''
            elif '/portal/' in path:
                html = self.portal
            elif '/life-account/' in path:
                html = '<a href="/content-creation/publish/short-video">发布视频</a>'
            else:
                html = '<input type="file" accept="video/*">'
            await route.fulfill(body=html, content_type='text/html; charset=utf-8')

        await self.page.unroute('**/*')
        await self.page.route('**/*', redirected_fixture)
        with patch('uploader.alipay_uploader.main.alipay_cookie_gen', AsyncMock()) as standalone:
            await self.uploader.open_upload_page(self.page, timeout=10)
        self.assertIn('/content-creation/publish/short-video', self.page.url)
        self.assertFalse(self.page.is_closed())
        self.assertEqual(len(self.page.context.pages), 1)
        self.assertEqual(sum('/life-account/' in url for url in visits), 2)
        standalone.assert_not_awaited()

    async def test_upload_route_alone_does_not_mean_form_is_ready(self):
        async def fixture(route):
            html = ('<a href="/content-creation/publish/short-video">发布视频</a>'
                    if '/life-account/' in route.request.url else '<div>加载中</div>')
            await route.fulfill(body=html, content_type='text/html; charset=utf-8')
        await self.page.unroute('**/*')
        await self.page.route('**/*', fixture)
        with self.assertRaisesRegex(RuntimeError, '发布页等待超时'):
            await self.uploader.open_upload_page(self.page, timeout=1)
        self.assertFalse(self.page.is_closed())

    async def test_upload_page_keeps_waiting_without_refreshing_qr_code(self):
        visits = []
        async def fixture(route):
            visits.append(route.request.url)
            await route.fulfill(body='<iframe title="login" srcdoc="扫码登录"></iframe>',
                                content_type='text/html; charset=utf-8')
        await self.page.unroute('**/*')
        await self.page.route('**/*', fixture)
        with self.assertRaisesRegex(RuntimeError, '发布页等待超时'):
            await self.uploader.open_upload_page(self.page, timeout=1)
        self.assertEqual(len(visits), 1)
        self.assertFalse(self.page.is_closed())

    def test_upload_page_wait_budget_is_fifteen_minutes(self):
        self.assertEqual(inspect.signature(AlipayVideo.open_upload_page).parameters['timeout'].default, 900)


if __name__ == '__main__':
    unittest.main()
