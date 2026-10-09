import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from playwright.async_api import async_playwright

from myUtils import login, postVideo
from uploader.pdd_uploader import main as pdd
from utils.browser_runtime import chromium_launch_options


def future_date():
    return (datetime.now(pdd.BEIJING) + timedelta(days=1)).replace(microsecond=0)


def video(**kwargs):
    return pdd.PDDVideo('标题', 'unused.mp4', ['#话题'], 'account.json',
                        content_declaration='含AI生成内容', **kwargs)


def form(target=None, declaration='含AI生成内容', mode=None):
    mode = mode or ('定时发布' if target else '立即发布')
    return f'''<section class="ContentDeclaration_statement_x">
        <div data-testid="beast-core-select" onclick="document.querySelector('#options').hidden=false">{declaration}</div>
        </section><div id="options" hidden>
          <div class="ContentDeclaration_title_x" onclick="document.querySelector('[data-testid=beast-core-select]').innerText=this.innerText;this.parentElement.hidden=true">含AI生成内容</div>
          <div class="ContentDeclaration_title_x">内容无需标注（作品不含AI生成、虚构、转载及营销等信息）</div>
        </div>
        <label><input name="mode" type="radio" {'checked' if mode == '立即发布' else ''}>立即发布</label>
        <label><input name="mode" type="radio" {'checked' if mode == '定时发布' else ''}>定时发布</label>
        <input data-testid="beast-core-datePicker-htmlInput" value="{target:%Y-%m-%d %H:%M:%S}">
        <button onclick="window.posts++;document.querySelector('#result').hidden=false">发布</button>
        <div id="result" hidden>发布成功</div><script>window.posts=0</script>''' if target else form(
            future_date(), declaration, mode=mode)


class PDDOptionsTests(unittest.TestCase):
    def test_default_is_dry_run_and_caption_preserves_content(self):
        uploader = video(description='描述')
        self.assertTrue(uploader.dry_run)
        self.assertEqual(uploader.caption, '标题\n描述\n#话题')

    def test_content_declaration_is_explicit(self):
        for declaration in (None, '', 'auto'):
            with self.assertRaisesRegex(ValueError, 'contentDeclaration'):
                pdd.validate_options(declaration, True)
        for declaration in pdd.CONTENT_DECLARATIONS:
            pdd.validate_options(declaration, False)

    def test_dry_run_string_cannot_enable_real_publishing(self):
        for value in ('false', 0, 1, None):
            with self.assertRaisesRegex(ValueError, 'dryRun'):
                pdd.validate_options('含AI生成内容', value)

    def test_schedule_offsets_and_precision(self):
        now = datetime(2030, 1, 1, tzinfo=pdd.BEIJING)
        local = pdd.normalize_publish_date('2030-01-01 12:34:56', now=now)
        utc = pdd.normalize_publish_date('2030-01-01T04:34:56Z', now=now)
        self.assertEqual(local, utc)
        for value in ('', None, 'wrong', now, now - timedelta(seconds=1), local.replace(microsecond=1)):
            with self.assertRaises(ValueError):
                pdd.normalize_publish_date(value, now=now)

    def test_session_requires_correct_cookie_domain_and_expiry(self):
        cookie = {'name': 'PDDAccessToken', 'domain': '.pinduoduo.com', 'value': 'test-only', 'expires': -1}
        self.assertTrue(pdd.has_personal_session([cookie]))
        for change in ({'name': 'tracking'}, {'domain': 'pinduoduo.com.evil.invalid'}, {'expires': 1}, {'value': ''}):
            self.assertFalse(pdd.has_personal_session([{**cookie, **change}]))

    @patch.object(postVideo, 'PDDVideo')
    @patch.object(postVideo.asyncio, 'run', return_value={'status': 'prepared', 'published': False, 'dryRun': True})
    def test_wiring_preserves_schedule_and_returns_prepared(self, run, publisher):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'video.mp4').touch()
            (root / 'account.json').touch()
            with patch.object(postVideo, 'VIDEO_FOLDER', root), patch.object(postVideo, 'COOKIES_FOLDER', root):
                result = postVideo.post_video_pdd('title', ['video.mp4'], [], ['account.json'],
                    enableTimer=True, endpublishTime=future_date().isoformat(), content_declaration='含AI生成内容')
        self.assertTrue(publisher.call_args.kwargs['dry_run'])
        self.assertIsInstance(publisher.call_args.kwargs['publish_date'], datetime)
        self.assertEqual(result['results'][0]['status'], 'prepared')
        self.assertFalse(result['results'][0]['published'])

    @patch.object(postVideo.asyncio, 'run')
    def test_adapter_rejects_invalid_options_before_browser(self, run):
        for extra in ({}, {'content_declaration': '含AI生成内容', 'enableTimer': True},
                      {'content_declaration': '含AI生成内容', 'dry_run': 'false'}):
            with self.assertRaises(ValueError):
                postVideo.post_video_pdd('title', ['video.mp4'], [], ['account.json'], **extra)
        with self.assertRaises(ValueError):
            postVideo.post_video_pdd('title', ['../video.mp4'], [], ['account.json'], content_declaration='含AI生成内容')
        run.assert_not_called()


class PDDLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_login_records_only_confirmed_personal_account(self):
        for success in (True, False):
            queue = Queue()
            with (
                tempfile.TemporaryDirectory() as directory,
                patch.object(login, 'COOKIES_FOLDER', Path(directory)),
                patch.object(login, 'pdd_browser_cookie_gen', AsyncMock(return_value={'success': success})) as browser_login,
                patch.object(login, '_record_account') as record,
            ):
                await login.pdd_cookie_gen('personal', queue)
                self.assertEqual(queue.get(), 'browser_opened')
                self.assertEqual(queue.get(), '200' if success else '500')
                browser_login.assert_awaited_once()
                if success:
                    self.assertEqual(record.call_args.args[0], 11)
                else:
                    record.assert_not_called()

    async def test_expired_login_resumes_and_saves_after_submit(self):
        events = []
        page = SimpleNamespace(goto=AsyncMock(), locator=Mock(return_value=SimpleNamespace(set_input_files=AsyncMock(), fill=AsyncMock())))
        context = SimpleNamespace(new_page=AsyncMock(return_value=page), close=AsyncMock())
        browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())
        runtime = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
        uploader = video()
        async def saved(*args):
            events.append('save')
        async def relogin(*args):
            events.append('login')
        async def submit(*args):
            events.append('submit')
            return {'status': 'prepared', 'published': False}
        with (
            patch.object(pdd.Path, 'is_file', return_value=True),
            patch.object(pdd, 'logged_in', AsyncMock(return_value=False)),
            patch.object(pdd, 'wait_for_login', AsyncMock(side_effect=relogin)),
            patch.object(pdd, 'save_session', AsyncMock(side_effect=saved)),
            patch.object(uploader, 'wait_upload', AsyncMock()),
            patch.object(uploader, 'set_declaration', AsyncMock()),
            patch.object(uploader, 'set_schedule', AsyncMock()),
            patch.object(uploader, 'submit', AsyncMock(side_effect=submit)),
        ):
            result = await uploader.upload(runtime)
        self.assertEqual(events, ['login', 'save', 'submit', 'save'])
        self.assertFalse(result['published'])
        page.goto.assert_awaited_once_with(pdd.PDD_PUBLISH_URL, wait_until='domcontentloaded', timeout=120000)
        browser.close.assert_awaited_once()

    async def test_failed_login_cannot_upload_and_browser_closes(self):
        file_input = SimpleNamespace(set_input_files=AsyncMock())
        page = SimpleNamespace(goto=AsyncMock(), locator=Mock(return_value=file_input))
        context = SimpleNamespace(new_page=AsyncMock(return_value=page), close=AsyncMock())
        browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())
        runtime = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
        with (
            patch.object(pdd.Path, 'is_file', return_value=True),
            patch.object(pdd, 'logged_in', AsyncMock(return_value=False)),
            patch.object(pdd, 'wait_for_login', AsyncMock(side_effect=TimeoutError('login'))),
        ):
            with self.assertRaises(TimeoutError):
                await video().upload(runtime)
        file_input.set_input_files.assert_not_awaited()
        browser.close.assert_awaited_once()

    async def test_browser_closed_even_if_context_cleanup_fails(self):
        context = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError('closed')))
        browser = SimpleNamespace(close=AsyncMock())
        await pdd.close_browser(context, browser)
        browser.close.assert_awaited_once()

    async def test_browser_cleanup_error_does_not_change_publication_result(self):
        context = SimpleNamespace(close=AsyncMock())
        browser = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError('close failed')))
        await pdd.close_browser(context, browser)
        browser.close.assert_awaited_once()

    async def test_failed_session_save_preserves_previous_state(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'account.json'
            destination.write_text('previous-test-state', encoding='utf-8')
            context = SimpleNamespace(storage_state=AsyncMock(side_effect=RuntimeError('save failed')))
            with self.assertRaises(RuntimeError):
                await pdd.save_session(context, destination)
            self.assertEqual(destination.read_text(encoding='utf-8'), 'previous-test-state')
            self.assertEqual(list(Path(directory).iterdir()), [destination])


class PDDFormTests(unittest.IsolatedAsyncioTestCase):
    """Local fixture pages only: no platform navigation or real uploads."""

    async def asyncSetUp(self):
        self.runtime = await async_playwright().start()
        self.browser = await self.runtime.chromium.launch(**chromium_launch_options(True))
        self.page = await self.browser.new_page()
        await self.page.route('**/*', lambda route: route.abort())

    async def asyncTearDown(self):
        await self.browser.close()
        await self.runtime.stop()

    async def test_selects_requested_declaration_not_no_label(self):
        await self.page.set_content(form(declaration='请选择'))
        await video().set_declaration(self.page, timeout=500)
        self.assertIn('含AI生成内容', await self.page.locator(pdd.STATEMENT).inner_text())
        self.assertEqual(await self.page.evaluate('window.posts'), 0)

    async def test_dry_run_never_clicks_publish(self):
        await self.page.set_content(form())
        result = await video().submit(self.page, timeout=0.3)
        self.assertEqual(result, {'status': 'prepared', 'published': False, 'dryRun': True})
        self.assertEqual(await self.page.evaluate('window.posts'), 0)

    async def test_dry_run_cannot_report_ready_without_enabled_publish_button(self):
        await self.page.set_content(form().replace('<button onclick=', '<button disabled onclick='))
        with self.assertRaisesRegex(RuntimeError, '发布按钮'):
            await video().submit(self.page, timeout=0.2)
        self.assertEqual(await self.page.evaluate('window.posts'), 0)

    async def test_page_validation_error_blocks_prepared_result(self):
        await self.page.set_content(form() + '<input aria-invalid="true">')
        with self.assertRaisesRegex(RuntimeError, '校验'):
            await video().submit(self.page, timeout=0.2)
        self.assertEqual(await self.page.evaluate('window.posts'), 0)

    async def test_wrong_declaration_blocks_real_publish(self):
        await self.page.set_content(form(declaration='内容无需标注'))
        with self.assertRaisesRegex(RuntimeError, '声明'):
            await video(dry_run=False).submit(self.page, timeout=0.3)
        self.assertEqual(await self.page.evaluate('window.posts'), 0)

    async def test_schedule_revert_cannot_publish_immediately(self):
        target = future_date()
        await self.page.set_content(form(target, mode='立即发布'))
        with self.assertRaisesRegex(RuntimeError, '发布方式'):
            await video(publish_date=target, dry_run=False).submit(self.page, timeout=0.3)
        self.assertEqual(await self.page.evaluate('window.posts'), 0)

    async def test_time_mismatch_blocks_publish(self):
        target = future_date()
        await self.page.set_content(form(target + timedelta(seconds=1)))
        with self.assertRaisesRegex(RuntimeError, '时间'):
            await video(publish_date=target, dry_run=False).submit(self.page, timeout=0.3)
        self.assertEqual(await self.page.evaluate('window.posts'), 0)

    async def test_schedule_expired_after_upload_blocks_publish(self):
        target = future_date()
        await self.page.set_content(form(target))
        uploader = video(publish_date=target, dry_run=False)
        uploader.publish_date = datetime.now(pdd.BEIJING) - timedelta(seconds=1)
        with self.assertRaises(ValueError):
            await uploader.submit(self.page, timeout=0.3)
        self.assertEqual(await self.page.evaluate('window.posts'), 0)

    async def test_immediate_submit_requires_new_visible_success(self):
        await self.page.set_content(form())
        result = await video(dry_run=False).submit(self.page, timeout=0.5)
        self.assertEqual(result['status'], 'published')
        self.assertEqual(await self.page.evaluate('window.posts'), 1)

    async def test_scheduled_submit_is_not_reported_as_public(self):
        target = future_date()
        await self.page.set_content(form(target))
        result = await video(publish_date=target, dry_run=False).submit(self.page, timeout=0.5)
        self.assertEqual(result['status'], 'scheduled')
        self.assertFalse(result['published'])

    async def test_disappearing_form_is_not_success(self):
        await self.page.set_content(form().replace("window.posts++;document.querySelector('#result').hidden=false", "window.posts++;this.remove()"))
        with self.assertRaisesRegex(TimeoutError, '结果未确认'):
            await video(dry_run=False).submit(self.page, timeout=0.2)
        self.assertEqual(await self.page.evaluate('window.posts'), 1)

    async def test_stale_success_prevents_duplicate_submission(self):
        await self.page.set_content(form().replace('id="result" hidden', 'id="result"'))
        with self.assertRaisesRegex(RuntimeError, '残留'):
            await video(dry_run=False).submit(self.page, timeout=0.2)
        self.assertEqual(await self.page.evaluate('window.posts'), 0)

    async def test_hidden_upload_success_does_not_finish_wait(self):
        await self.page.set_content('<p hidden>视频上传成功</p>')
        with self.assertRaises(TimeoutError):
            await video().wait_upload(self.page, timeout=0.1)

    async def test_editable_calendar_confirms_and_checks_seconds(self):
        target = future_date()
        await self.page.set_content(form(target).replace(
            'data-testid="beast-core-datePicker-htmlInput"',
            'onfocus="document.querySelector(\'#picker\').hidden=false" data-testid="beast-core-datePicker-htmlInput"') + '''
            <div id="picker" data-testid="beast-core-datePicker-dropdown-contentRoot" hidden>
              <button onclick="this.parentElement.hidden=true">确认</button></div>''')
        await video(publish_date=target).set_schedule(self.page, timeout=500)
        self.assertEqual(await self.page.locator(pdd.DATE_INPUT).input_value(), target.strftime('%Y-%m-%d %H:%M:%S'))
        self.assertEqual(await self.page.evaluate('window.posts'), 0)

    async def test_readonly_calendar_picks_correct_month_day_and_time(self):
        target = future_date()
        await self.page.set_content(form(target).replace(
            'data-testid="beast-core-datePicker-htmlInput"',
            'readonly onfocus="document.querySelector(\'#picker\').hidden=false" data-testid="beast-core-datePicker-htmlInput"') + f'''
            <div id="picker" data-testid="beast-core-datePicker-dropdown-contentRoot" hidden>
              <section data-testid="beast-core-datePicker-dropdown-header">{target.year}年 {target.month}月</section>
              <table data-testid="beast-core-datePicker-table"><tr>
                <td class="RPR_outOfMonth_x" onclick="window.wrong=true">{target.day}</td>
                <td onclick="window.day={target.day}">{target.day}</td>
              </tr></table>
              <input data-testid="beast-core-timePicker-html-input" readonly>
              <ul class="TPK_ul_x"><li class="cIL_item_x" onclick="window.hour={target.hour}">{target.hour:02d}</li></ul>
              <ul class="TPK_ul_x"><li class="cIL_item_x" onclick="window.minute={target.minute}">{target.minute:02d}</li></ul>
              <ul class="TPK_ul_x"><li class="cIL_item_x" onclick="window.second={target.second}">{target.second:02d}</li></ul>
              <button onclick="document.querySelector('[data-testid=beast-core-datePicker-htmlInput]').value=
                '{target.year}-{target.month:02d}-'+String(window.day).padStart(2,'0')+' '+
                [window.hour,window.minute,window.second].map(n=>String(n).padStart(2,'0')).join(':');
                this.parentElement.hidden=true">确认</button></div>''')
        await self.page.locator(pdd.DATE_INPUT).evaluate("element => element.value = ''")
        await video(publish_date=target).set_schedule(self.page, timeout=500)
        self.assertEqual(await self.page.evaluate('[window.day,window.hour,window.minute,window.second]'),
                         [target.day, target.hour, target.minute, target.second])
        self.assertIsNone(await self.page.evaluate('window.wrong'))

    async def test_login_shell_without_cookie_is_not_authenticated(self):
        await self.page.set_content('<button>添加视频</button><div>退出登录</div><input type="file" accept=".mp4">')
        context = SimpleNamespace(cookies=AsyncMock(return_value=[]))
        scoped = SimpleNamespace(url=pdd.PDD_PUBLISH_URL, get_by_text=self.page.get_by_text,
                                 get_by_role=self.page.get_by_role, locator=self.page.locator)
        self.assertFalse(await pdd.logged_in(scoped, context))

    async def test_login_requires_session_and_loaded_page_not_just_url(self):
        await self.page.set_content('<button>添加视频</button><div>退出登录</div><input type="file" accept=".mp4"><p id="loading">加载中...</p>')
        context = SimpleNamespace(cookies=AsyncMock(return_value=[{
            'name': 'PDDAccessToken', 'domain': '.pinduoduo.com', 'value': 'test-only', 'expires': -1}]))
        scoped = SimpleNamespace(url=pdd.PDD_PUBLISH_URL, get_by_text=self.page.get_by_text,
                                 get_by_role=self.page.get_by_role, locator=self.page.locator)
        self.assertFalse(await pdd.logged_in(scoped, context))
        await self.page.locator('#loading').evaluate('element => element.remove()')
        self.assertTrue(await pdd.logged_in(scoped, context))
        scoped.url = 'https://mms.pinduoduo.com/home'
        self.assertFalse(await pdd.logged_in(scoped, context))

    async def test_calendar_disabled_date_cannot_be_selected(self):
        target = future_date()
        await self.page.set_content(f'''<div data-testid="beast-core-datePicker-dropdown-contentRoot">
            <section data-testid="beast-core-datePicker-dropdown-header">{target.year}年 {target.month}月</section>
            <table data-testid="beast-core-datePicker-table"><tr>
              <td class="RPR_disabled_x">{target.day}</td>
              <td class="RPR_outOfMonth_x">{target.day}</td></tr></table></div>''')
        with self.assertRaisesRegex(ValueError, '不可选'):
            await video().pick_datetime(self.page, self.page.locator(pdd.PICKER), target, 500)

    async def test_calendar_navigation_preserves_year_across_december(self):
        target = datetime(2031, 1, 2, 12, 34, 56, tzinfo=pdd.BEIJING)
        await self.page.set_content('''<div data-testid="beast-core-datePicker-dropdown-contentRoot">
            <section data-testid="beast-core-datePicker-dropdown-header"><span id="month">2030年 12月</span>
              <button data-testid="beast-core-icon-right" onclick="document.querySelector('#month').innerText='2031年 1月'"></button>
            </section><table data-testid="beast-core-datePicker-table"><tr><td onclick="window.day=2">2</td></tr></table>
            <input data-testid="beast-core-timePicker-html-input" readonly>
            <ul class="TPK_ul_x"><li class="cIL_item_x">12</li></ul>
            <ul class="TPK_ul_x"><li class="cIL_item_x">34</li></ul>
            <ul class="TPK_ul_x"><li class="cIL_item_x">56</li></ul></div>''')
        await video().pick_datetime(self.page, self.page.locator(pdd.PICKER), target, 500)
        self.assertEqual(await self.page.locator('#month').inner_text(), '2031年 1月')
        self.assertEqual(await self.page.evaluate('window.day'), 2)

    async def test_calendar_missing_seconds_stops_instead_of_publishing(self):
        target = future_date()
        await self.page.set_content(f'''<div data-testid="beast-core-datePicker-dropdown-contentRoot">
            <section data-testid="beast-core-datePicker-dropdown-header">{target.year}年 {target.month}月</section>
            <table data-testid="beast-core-datePicker-table"><tr><td>{target.day}</td></tr></table>
            <input data-testid="beast-core-timePicker-html-input" readonly>
            <ul class="TPK_ul_x"></ul><ul class="TPK_ul_x"></ul></div>''')
        with self.assertRaisesRegex(RuntimeError, '时分秒'):
            await video().pick_datetime(self.page, self.page.locator(pdd.PICKER), target, 500)


if __name__ == '__main__':
    unittest.main()
