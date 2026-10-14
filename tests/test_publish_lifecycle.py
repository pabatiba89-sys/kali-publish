import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from playwright.async_api import Error, async_playwright

from utils.browser_runtime import chromium_launch_options
from utils.publish_lifecycle import close_owned_browser, navigation_read
from uploader.alipay_uploader.main import AlipayVideo
from uploader.alipay_uploader.main import _cookie_auth
from uploader.web_publishers import InstagramWebVideo


class PublishLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_alipay_cookie_probe_ignores_hidden_login_frame_but_requires_entry(self):
        for visible_login, entry_ready, expected in ((0, True, True), (1, True, False), (0, False, False)):
            page = Mock(url='https://c.alipay.com/page/life-account/index',
                        goto=AsyncMock(), wait_for_timeout=AsyncMock())
            frame = SimpleNamespace(count=AsyncMock(return_value=visible_login))
            entry = SimpleNamespace(is_visible=AsyncMock(return_value=entry_ready),
                                    is_enabled=AsyncMock(return_value=True))
            page.locator.side_effect = [frame, SimpleNamespace(first=entry)]
            context = SimpleNamespace(new_page=AsyncMock(return_value=page), pages=[], close=AsyncMock())
            browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())
            runtime = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
            with patch('uploader.alipay_uploader.main.Path.is_file', return_value=True):
                self.assertEqual(await _cookie_auth(runtime, 'unused'), expected)
            browser.close.assert_awaited_once()

    async def test_navigation_reads_retry_but_other_errors_do_not(self):
        read = AsyncMock(side_effect=[Error('Execution context was destroyed'), 1])
        self.assertEqual(await navigation_read(read), 1)
        self.assertEqual(read.await_count, 2)
        for text in ('Target page has been closed', 'permission denied'):
            read = AsyncMock(side_effect=Error(text))
            with self.assertRaises(Error):
                await navigation_read(read)
            read.assert_awaited_once()

    async def test_navigation_retry_is_bounded(self):
        with self.assertRaises(Error):
            await navigation_read(AsyncMock(side_effect=Error('Execution context was destroyed')), timeout=0)

    async def test_cleanup_closes_pages_and_uses_only_owned_browser_cdp(self):
        session = SimpleNamespace(send=AsyncMock())
        page = SimpleNamespace(close=AsyncMock())
        context = SimpleNamespace(pages=[page], close=AsyncMock(side_effect=TimeoutError()))
        browser = SimpleNamespace(new_browser_cdp_session=AsyncMock(return_value=session),
                                  close=AsyncMock(side_effect=TimeoutError()), is_connected=lambda: False)
        await close_owned_browser(context, browser, Mock(), timeout=0.01)
        page.close.assert_awaited_once_with(run_before_unload=False)
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()
        session.send.assert_awaited_once_with('Browser.close')

    async def test_alipay_submit_navigation_error_still_saves_cookie(self):
        page = Mock(url='https://c.alipay.com/content-creation/publish/short-video')
        button = page.get_by_role.return_value.first
        button.click = AsyncMock()
        result = page.get_by_text.return_value.locator.return_value
        calls = 0

        async def navigating_read():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise Error('Locator.count: Execution context was destroyed, most likely because of a navigation')
            return 1

        result.count = navigating_read
        context = SimpleNamespace(new_page=AsyncMock(return_value=page), pages=[],
                                  storage_state=AsyncMock(), close=AsyncMock())
        browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())
        runtime = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
        uploader = AlipayVideo('title', 'unused', [], 'account.json')
        with patch('uploader.alipay_uploader.main.Path.is_file', return_value=True), \
             patch('uploader.alipay_uploader.main._cookie_auth', AsyncMock(return_value=True)), \
             patch.object(uploader, 'open_upload_page', AsyncMock()), \
             patch.object(uploader, 'fill_form', AsyncMock()), \
             patch.object(uploader, 'wait_upload', AsyncMock()):
            await uploader.upload(runtime)
        button.click.assert_awaited_once()
        context.storage_state.assert_awaited_once_with(path='account.json')
        browser.close.assert_awaited_once()

    async def test_ins_cookie_save_failure_is_not_a_failed_post(self):
        page = Mock(set_viewport_size=AsyncMock())
        context = SimpleNamespace(new_page=AsyncMock(return_value=page), pages=[],
                                  storage_state=AsyncMock(side_effect=RuntimeError('disk error')),
                                  close=AsyncMock())
        browser = SimpleNamespace(close=AsyncMock())
        uploader = InstagramWebVideo('title', 'unused', [], 'account.json')
        with patch('uploader.web_publishers.Path.is_file', return_value=True), \
             patch('uploader.web_publishers._browser_cookie_auth', AsyncMock(return_value=True)), \
             patch('uploader.web_publishers._open_account_context', AsyncMock(return_value=(context, browser))), \
             patch('uploader.web_publishers.set_init_script', AsyncMock(return_value=context)), \
             patch.object(uploader, 'publish', AsyncMock()) as publish:
            await uploader.upload(Mock())
        publish.assert_awaited_once()
        page.screenshot.assert_not_called()
        browser.close.assert_awaited_once()


class RealBrowserLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_cdp_fallback_closes_owned_browser_not_another_browser(self):
        async with async_playwright() as runtime:
            owned = await runtime.chromium.launch(**chromium_launch_options(True))
            other = await runtime.chromium.launch(**chromium_launch_options(True))
            try:
                context = await owned.new_context()
                page = await context.new_page()
                await page.set_content('<p>Local test only</p>')
                with patch.object(owned, 'close', AsyncMock(side_effect=TimeoutError())):
                    await close_owned_browser(context, owned, Mock(), timeout=2)
                for _ in range(20):
                    if not owned.is_connected():
                        break
                    await asyncio.sleep(0.05)
                self.assertFalse(owned.is_connected())
                self.assertTrue(other.is_connected())
            finally:
                await owned.close()
                await other.close()

    async def test_alipay_navigation_then_cookie_saved_to_original_file(self):
        async with async_playwright() as runtime:
            browser = await runtime.chromium.launch(**chromium_launch_options(True))
            context = await browser.new_context()
            page = await context.new_page()
            async def fixture(route):
                html = ('<button onclick="location.href=\'/content-creation/posts\'">确认发布</button>'
                        if 'short-video' in route.request.url else '<h2>作品列表</h2>')
                await route.fulfill(body=html, content_type='text/html; charset=utf-8')
            await page.route('**/*', fixture)
            try:
                await context.add_cookies([{'name': 'fixture', 'value': 'test-only', 'url': 'https://c.alipay.com'}])
                await page.goto('https://c.alipay.com/content-creation/publish/short-video')
                with tempfile.TemporaryDirectory() as directory:
                    target = Path(directory) / 'account.json'
                    uploader = AlipayVideo('title', 'unused', [], str(target))
                    await uploader.submit(page, timeout=3)
                    await context.storage_state(path=target)
                    self.assertTrue(target.is_file())
                    import json
                    self.assertEqual(json.loads(target.read_text())['cookies'][0]['name'], 'fixture')
            finally:
                await browser.close()
