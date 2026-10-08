import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from uploader.alipay_uploader.main import AlipayVideo, format_title_with_tags


class AlipayUploaderTests(unittest.TestCase):
    def test_title_tags_are_added_only_at_tag_boundaries(self):
        self.assertEqual(
            format_title_with_tags("1234567890", ["abc", "too-long"], max_length=15),
            "1234567890 #abc",
        )

    def test_long_title_is_truncated(self):
        self.assertEqual(format_title_with_tags("123456", [], max_length=4), "1234")


class AlipayCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def run_login_flow(self, auth_results, login_success, expect_error=False):
        events = []
        async def save_state(**kwargs):
            events.append('save_cookie')
        async def submit(page):
            events.append('publish')
        context = SimpleNamespace(new_page=AsyncMock(), storage_state=AsyncMock(side_effect=save_state), close=AsyncMock())
        browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())
        runtime = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
        uploader = AlipayVideo('title', 'unused', [], 'account.json')
        with (
            patch('uploader.alipay_uploader.main.Path.is_file', return_value=True),
            patch('uploader.alipay_uploader.main._cookie_auth', AsyncMock(side_effect=auth_results)),
            patch('uploader.alipay_uploader.main.alipay_cookie_gen', AsyncMock(return_value={'success': login_success})) as login,
            patch.object(uploader, 'open_upload_page', AsyncMock()),
            patch.object(uploader, 'fill_form', AsyncMock()),
            patch.object(uploader, 'wait_upload', AsyncMock()),
            patch.object(uploader, 'submit', AsyncMock(side_effect=submit)),
        ):
            if expect_error:
                with self.assertRaisesRegex(RuntimeError, '登录'):
                    await uploader.upload(runtime)
                runtime.chromium.launch.assert_not_awaited()
            else:
                await uploader.upload(runtime)
                context.storage_state.assert_awaited_once_with(path='account.json')
                browser.close.assert_awaited_once()
        return events, login

    async def test_expired_session_logs_in_then_publishes_and_refreshes_cookie(self):
        events, login = await self.run_login_flow([False, True], True)
        self.assertEqual(events, ['publish', 'save_cookie'])
        login.assert_awaited_once_with('account.json', headless=False)

    async def test_valid_session_does_not_open_login(self):
        events, login = await self.run_login_flow([True], True)
        login.assert_not_awaited()
        self.assertEqual(events, ['publish', 'save_cookie'])

    async def test_cancelled_login_does_not_publish(self):
        events, login = await self.run_login_flow([False], False, expect_error=True)
        login.assert_awaited_once()
        self.assertEqual(events, [])

    async def test_unusable_refreshed_cookie_does_not_publish(self):
        events, login = await self.run_login_flow([False, False], True, expect_error=True)
        login.assert_awaited_once()
        self.assertEqual(events, [])

    async def test_browser_closed_even_if_context_close_raises(self):
        context = SimpleNamespace(new_page=AsyncMock(), storage_state=AsyncMock(),
                                  close=AsyncMock(side_effect=RuntimeError('context close failed')))
        browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())
        runtime = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
        uploader = AlipayVideo('title', 'unused', [], 'unused')
        with (
            patch('uploader.alipay_uploader.main.Path.is_file', return_value=True),
            patch('uploader.alipay_uploader.main._cookie_auth', AsyncMock(return_value=True)),
            patch.object(uploader, 'open_upload_page', AsyncMock()),
            patch.object(uploader, 'fill_form', AsyncMock()),
            patch.object(uploader, 'wait_upload', AsyncMock()),
            patch.object(uploader, 'submit', AsyncMock()),
        ):
            await uploader.upload(runtime)
        browser.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
