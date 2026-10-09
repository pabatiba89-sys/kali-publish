import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from uploader.alipay_uploader.main import AlipayVideo, format_title_with_tags
import uploader.alipay_uploader.main as alipay


class AlipayUploaderTests(unittest.TestCase):
    def test_schedule_limits_and_minute_precision(self):
        now = datetime(2030, 1, 1, 10, tzinfo=timezone(timedelta(hours=8)))
        for delta in (timedelta(minutes=15), timedelta(days=14)):
            self.assertEqual(alipay.normalize_publish_date(now + delta, now=now), now + delta)
        for delta in (timedelta(minutes=14), timedelta(days=14, minutes=1), timedelta(minutes=-1)):
            with self.assertRaisesRegex(ValueError, '15.*14'):
                alipay.normalize_publish_date(now + delta, now=now)
        with self.assertRaisesRegex(ValueError, '分钟'):
            alipay.normalize_publish_date(now + timedelta(hours=1, seconds=30), now=now)

    def test_schedule_uses_beijing_time_and_preserves_explicit_instant(self):
        now = datetime(2030, 1, 1, 10, tzinfo=timezone(timedelta(hours=8)))
        local = alipay.normalize_publish_date('2030-01-01 11:00:00', now=now)
        explicit = alipay.normalize_publish_date('2030-01-01T03:00:00Z', now=now)
        self.assertEqual(local, explicit)
        self.assertEqual(local.hour, 11)

    def test_missing_or_invalid_schedule_is_rejected(self):
        for value in ('', None, 'not a date'):
            with self.assertRaisesRegex(ValueError, '时间'):
                alipay.normalize_publish_date(value)

    def test_title_tags_are_added_only_at_tag_boundaries(self):
        self.assertEqual(
            format_title_with_tags("1234567890", ["abc", "too-long"], max_length=15),
            "1234567890 #abc",
        )

    def test_long_title_is_truncated(self):
        self.assertEqual(format_title_with_tags("123456", [], max_length=4), "1234")


class AlipayCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_schedule_does_not_submit_and_closes_browser(self):
        context = SimpleNamespace(new_page=AsyncMock(), storage_state=AsyncMock(), close=AsyncMock())
        browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())
        runtime = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
        uploader = AlipayVideo('title', 'unused', [], 'account.json')
        with (
            patch('uploader.alipay_uploader.main.Path.is_file', return_value=True),
            patch('uploader.alipay_uploader.main._cookie_auth', AsyncMock(return_value=True)),
            patch.object(uploader, 'open_upload_page', AsyncMock()),
            patch.object(uploader, 'fill_form', AsyncMock()),
            patch.object(uploader, 'wait_upload', AsyncMock()),
            patch.object(uploader, 'apply_schedule', AsyncMock(side_effect=RuntimeError('定时设置失败'))),
            patch.object(uploader, 'submit', AsyncMock()) as submit,
        ):
            with self.assertRaisesRegex(RuntimeError, '定时'):
                await uploader.upload(runtime)
        submit.assert_not_awaited()
        context.storage_state.assert_not_awaited()
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()

    async def run_login_flow(self, auth_results, login_success, expect_error=False, publish_error=False):
        events = []
        page = object()
        async def login_page(actual_page):
            self.assertIs(actual_page, page)
            events.append('login')
            if not login_success:
                raise RuntimeError('登录取消')
        async def open_page(actual_page):
            self.assertIs(actual_page, page)
            events.append('open_upload')
            if len(auth_results) > 1 and not auth_results[1]:
                raise RuntimeError('登录后发布页不可用')
        async def save_state(**kwargs):
            events.append('save_cookie')
        async def submit(actual_page):
            self.assertIs(actual_page, page)
            events.append('publish')
            if publish_error:
                raise RuntimeError('发布失败')
        async def close_context():
            events.append('close_context')
        async def close_browser():
            events.append('close_browser')
        context = SimpleNamespace(new_page=AsyncMock(return_value=page), storage_state=AsyncMock(side_effect=save_state), close=AsyncMock(side_effect=close_context))
        browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock(side_effect=close_browser))
        runtime = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
        uploader = AlipayVideo('title', 'unused', [], 'account.json', headless=True)
        with (
            patch('uploader.alipay_uploader.main.Path.is_file', return_value=True),
            patch('uploader.alipay_uploader.main._cookie_auth', AsyncMock(return_value=auth_results[0])) as auth,
            patch('uploader.alipay_uploader.main.alipay_cookie_gen', AsyncMock()) as standalone_login,
            patch.object(uploader, 'login_for_publish', AsyncMock(side_effect=login_page)) as login,
            patch.object(uploader, 'open_upload_page', AsyncMock(side_effect=open_page)),
            patch.object(uploader, 'fill_form', AsyncMock()),
            patch.object(uploader, 'wait_upload', AsyncMock()),
            patch.object(uploader, 'submit', AsyncMock(side_effect=submit)),
        ):
            if expect_error:
                with self.assertRaisesRegex(RuntimeError, '登录|发布'):
                    await uploader.upload(runtime)
                context.storage_state.assert_not_awaited()
            else:
                await uploader.upload(runtime)
                context.storage_state.assert_awaited_once_with(path='account.json')
        runtime.chromium.launch.assert_awaited_once()
        self.assertEqual(runtime.chromium.launch.call_args.kwargs['headless'], auth_results[0])
        browser.new_context.assert_awaited_once_with(**({'storage_state': 'account.json'} if auth_results[0] else {}))
        context.new_page.assert_awaited_once()
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()
        auth.assert_awaited_once()
        standalone_login.assert_not_awaited()
        return events, login, page

    async def test_expired_session_logs_in_then_publishes_and_refreshes_cookie(self):
        events, login, page = await self.run_login_flow([False, True], True)
        self.assertEqual(events, ['login', 'open_upload', 'publish', 'save_cookie', 'close_context', 'close_browser'])
        login.assert_awaited_once_with(page)

    async def test_valid_session_does_not_open_login(self):
        events, login, _ = await self.run_login_flow([True], True)
        login.assert_not_awaited()
        self.assertEqual(events, ['open_upload', 'publish', 'save_cookie', 'close_context', 'close_browser'])

    async def test_cancelled_login_does_not_publish(self):
        events, login, _ = await self.run_login_flow([False], False, expect_error=True)
        login.assert_awaited_once()
        self.assertEqual(events, ['login', 'close_context', 'close_browser'])

    async def test_unusable_refreshed_cookie_does_not_publish(self):
        events, login, _ = await self.run_login_flow([False, False], True, expect_error=True)
        login.assert_awaited_once()
        self.assertEqual(events, ['login', 'open_upload', 'close_context', 'close_browser'])

    async def test_failed_publication_does_not_overwrite_saved_cookie(self):
        events, _, _ = await self.run_login_flow([False, True], True, expect_error=True, publish_error=True)
        self.assertEqual(events, ['login', 'open_upload', 'publish', 'close_context', 'close_browser'])

    async def test_standalone_login_still_saves_cookie_and_closes(self):
        iframe = SimpleNamespace(count=AsyncMock(return_value=1))
        page = SimpleNamespace(goto=AsyncMock(), locator=MagicMock(return_value=iframe),
                               wait_for_timeout=AsyncMock(), url=alipay.ALIPAY_PORTAL_HOME)
        context = SimpleNamespace(new_page=AsyncMock(return_value=page), storage_state=AsyncMock(), close=AsyncMock())
        browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())
        runtime = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=runtime)
        manager.__aexit__ = AsyncMock(return_value=False)
        with (
            patch.object(alipay, 'async_playwright', return_value=manager),
            patch.object(alipay, '_login_complete', AsyncMock(return_value=True)),
            patch.object(alipay.Path, 'mkdir'),
            patch.object(alipay.Path, 'chmod'),
        ):
            result = await alipay.alipay_cookie_gen('standalone-account.json')
        self.assertTrue(result['success'])
        context.storage_state.assert_awaited_once_with(path=alipay.Path('standalone-account.json'))
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()

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
