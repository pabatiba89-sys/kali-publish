"""Offline product-selection fixtures; never navigate to or post on WeChat."""
import tempfile
import unittest
import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from flask import Flask
from playwright.async_api import async_playwright

from db import connect, initialize
from myUtils import postVideo
from uploader.tencent_uploader.main import TencentVideo, LAOLU_PRODUCT_ID, LAOLU_PRODUCT_NAME, PRODUCT_TIMEOUT_MS
from utils.browser_runtime import chromium_launch_options


def video(name='老陆出海', scheduled=False):
    return TencentVideo('title', 'unused.mp4', [], '2026-12-01 12:00:00', 'unused.json',
                        enableTimer=scheduled, account_name=name)


def fixture(product_id=LAOLU_PRODUCT_ID, name=LAOLU_PRODUCT_NAME, attach=True, disabled=False,
            confirm_label='添加(1)', confirm_tag='button', timing_delay=0, manual_timing=False,
            stuck_timing=False, disabled_timing=False):
    timing_action = ("document.querySelector('#edit-timing').hidden=false" if manual_timing else
                     f"setTimeout(()=>document.querySelector('#timing').hidden=false,{timing_delay})")
    close_action = 'void(0)' if stuck_timing else "document.querySelector('#timing').hidden=true"
    return f'''<div class="form"><div class="input-editor"></div>
      <button onclick="document.querySelector('#menu').hidden=false">选择链接</button>
      <div id="menu" hidden><button onclick="this.parentElement.hidden=true;
        document.querySelector('#picker').hidden=false">商品</button></div>
      <button id="picker" hidden onclick="document.querySelector('[role=dialog]').hidden=false">
        选择需要添加的商品</button><div id="attached"></div>
        <a id="edit-timing" hidden onclick="document.querySelector('#timing').hidden=false">修改商品出现时机</a>
      </div>
      <div role="dialog" hidden>
        <button>从橱窗添加商品</button>
        <input placeholder="请输入商品名称/编码搜索">
        <button onclick="window.search=document.querySelector('input').value;
          setTimeout(()=>document.querySelector('#rows').hidden=false,100)">筛选</button>
        <div id="rows" hidden>
          <div><input type="radio" name="goods" value="wrong"><span>其他商品</span><span>ID 999</span></div>
          <div id="target"><input type="radio" name="goods" value="course" {'disabled' if disabled else ''}>
            <span>{name}</span><span>ID {product_id}</span></div>
        </div>
        <{confirm_tag} onclick="window.adds++; document.querySelector('[role=dialog]').hidden=true;
          document.querySelector('#attached').textContent={'JSON.stringify(null)' if not attach else repr(name)};
          {timing_action}">
          {confirm_label}</{confirm_tag}>
      </div>
      <div id="timing" class="weui-desktop-dialog__wrp" hidden>
        <div role="dialog"><h2>选择商品出现时机</h2>
          <div onclick="window.seconds=5">视频播放5秒后出现</div>
          <div onclick="window.seconds=99">自定义出现时机</div>
        </div>
        <div><button onclick="window.cancels++">取消</button>
          <button {'disabled' if disabled_timing else ''} onclick="window.confirms++;
            {close_action}">确认</button></div>
      </div>
      <button onclick="window.unrelated++">确认</button>
      <div hidden>{LAOLU_PRODUCT_NAME}</div>
      <button onclick="window.posts++">发表</button>
      <script>window.posts=0;window.adds=0;window.confirms=0;window.seconds=99;
        window.cancels=0;window.unrelated=0;</script>'''


class TencentProductFormTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runtime = await async_playwright().start()
        self.browser = await self.runtime.chromium.launch(**chromium_launch_options(True))
        self.page = await self.browser.new_page()
        await self.page.route('**/*', lambda route: route.abort())

    async def asyncTearDown(self):
        await self.browser.close()
        await self.runtime.stop()

    async def test_adds_exact_course_once_by_id_for_each_laolu_name(self):
        for name in ('老陆', '老陆出海', '老陆本人'):
            with self.subTest(name=name):
                await self.page.set_content(fixture())
                await video(name).add_required_product(self.page, timeout=5000)
                self.assertEqual(await self.page.evaluate('window.search'), LAOLU_PRODUCT_ID)
                self.assertEqual(await self.page.evaluate('window.adds'), 1)
                self.assertEqual(await self.page.evaluate('window.posts'), 0)
                self.assertEqual(await self.page.evaluate('[window.confirms,window.seconds,window.unrelated,window.cancels]'),
                                 [1, 5, 0, 0])
                self.assertTrue(await self.page.locator('#target input').is_checked())
                self.assertFalse(await self.page.locator('input[value=wrong]').is_checked())

    async def test_custom_confirmation_controls_and_delayed_timing(self):
        for label, tag in [('确认', 'div'), ('确 定', 'a'), ('添加（ 1 ）', 'button')]:
            with self.subTest(label=label):
                await self.page.set_content(fixture(confirm_label=label, confirm_tag=tag, timing_delay=600))
                await video().add_required_product(self.page, timeout=5000)
                self.assertEqual(await self.page.evaluate('[window.adds,window.confirms,window.seconds,window.unrelated]'),
                                 [1, 1, 5, 0])

    async def test_split_id_label_and_hidden_duplicate_do_not_block_selection(self):
        html = fixture().replace(f'<span>ID {LAOLU_PRODUCT_ID}</span>',
                                f'<div><span>ID</span> <span>{LAOLU_PRODUCT_ID}</span></div>')
        html = html.replace('<div id="rows" hidden>',
                            f'<div hidden>ID {LAOLU_PRODUCT_ID}</div><div id="rows" hidden>')
        await self.page.set_content(html)
        await video().add_required_product(self.page, timeout=5000)
        self.assertTrue(await self.page.locator('#target input').is_checked())
        self.assertEqual(await self.page.evaluate('[window.adds,window.confirms]'), [1, 1])

    async def test_checkbox_is_checked_and_preselected_hidden_checkbox_is_not_toggled(self):
        for selected in (False, True):
            with self.subTest(selected=selected):
                html = fixture().replace('type="radio" name="goods" value="course"',
                    'type="checkbox" name="goods" value="course"' +
                    (' checked style="display:none"' if selected else ''))
                html = html.replace('<div id="target">',
                    '<div id="target" onclick="if(event.target===this) '
                    'this.querySelector(\'input\').checked=!this.querySelector(\'input\').checked">')
                await self.page.set_content(html)
                await video().add_required_product(self.page, timeout=5000)
                self.assertTrue(await self.page.locator('#target input').is_checked())
                self.assertEqual(await self.page.evaluate('[window.adds,window.confirms]'), [1, 1])

    async def test_add_one_label_without_a_checked_product_does_not_confirm(self):
        html = fixture().replace('type="radio" name="goods" value="course"',
                                'type="checkbox" name="goods" value="course" style="display:none"')
        await self.page.set_content(html)
        with self.assertRaisesRegex(RuntimeError, '选中指定商品'):
            await video().add_required_product(self.page, timeout=1200)
        self.assertEqual(await self.page.evaluate('[window.adds,window.confirms,window.posts]'), [0, 0, 0])

    async def test_zero_selected_label_is_allowed_before_selection_only(self):
        html = fixture(confirm_label='添加(0)').replace(
            'name="goods" value="course"',
            'name="goods" value="course" onchange="document.querySelector(\'[role=dialog] > button:last-child\').textContent=\'添加(1)\'"')
        await self.page.set_content(html)
        await video().add_required_product(self.page, timeout=5000)
        self.assertEqual(await self.page.evaluate('[window.adds,window.confirms]'), [1, 1])

    async def test_picker_with_plain_add_label_does_not_require_manual_selection(self):
        html = fixture(confirm_label='添加').replace(
            'name="goods" value="course"',
            'name="goods" value="course" onchange="document.querySelector(\'[role=dialog] > button:last-child\').textContent=\'添加(1)\'"')
        await self.page.set_content(html)
        await video().add_required_product(self.page, timeout=5000)
        self.assertTrue(await self.page.locator('#target input').is_checked())
        self.assertEqual(await self.page.evaluate('[window.adds,window.confirms]'), [1, 1])

    async def test_plain_add_confirms_only_after_real_selection(self):
        await self.page.set_content(fixture(confirm_label='添加'))
        await video().add_required_product(self.page, timeout=5000)
        self.assertTrue(await self.page.locator('#target input').is_checked())
        self.assertEqual(await self.page.evaluate('[window.adds,window.confirms]'), [1, 1])

    async def test_publish_submits_once_and_accepts_list_query_parameters(self):
        html = '''<div class="form-btns"><button onclick="window.posts++;
          setTimeout(()=>history.pushState({},'', '/platform/post/list?tab=video'), 200)">发表</button></div>
          <script>window.posts=0</script>'''
        await self.page.route('**/*', lambda route: route.fulfill(body=html, content_type='text/html; charset=utf-8'))
        await self.page.goto('https://channels.weixin.qq.com/platform/post/create')
        await asyncio.wait_for(video().click_publish(self.page), timeout=3)
        self.assertEqual(await self.page.evaluate('window.posts'), 1)

    async def test_can_open_timing_from_explicit_edit_link(self):
        await self.page.set_content(fixture(manual_timing=True))
        await video().add_required_product(self.page, timeout=5000)
        self.assertEqual(await self.page.evaluate('[window.adds,window.confirms,window.seconds]'), [1, 1, 5])

    async def test_timing_must_close_after_confirmation(self):
        await self.page.set_content(fixture(stuck_timing=True))
        with self.assertRaisesRegex(RuntimeError, '停止发布'):
            await video().add_required_product(self.page, timeout=5000)
        self.assertEqual(await self.page.evaluate('[window.adds,window.confirms,window.posts]'), [1, 1, 0])

    async def test_disabled_timing_confirmation_is_not_forced(self):
        await self.page.set_content(fixture(disabled_timing=True))
        with self.assertRaisesRegex(RuntimeError, '停止发布'):
            await video().add_required_product(self.page, timeout=5000)
        self.assertEqual(await self.page.evaluate('[window.adds,window.confirms,window.posts]'), [1, 0, 0])

    async def test_other_accounts_do_not_touch_product_ui(self):
        for name in ('岳同学AI', '陆老师', ''):
            page = Mock()
            await video(name).add_required_product(page)
            self.assertEqual(page.mock_calls, [])

    async def test_no_fallback_to_same_name_with_different_id(self):
        await self.page.set_content(fixture(product_id=LAOLU_PRODUCT_ID + '9'))
        with self.assertRaisesRegex(RuntimeError, '停止发布'):
            await video().add_required_product(self.page, timeout=5000)
        self.assertEqual(await self.page.evaluate('window.adds'), 0)

    async def test_matching_id_with_wrong_name_is_rejected(self):
        await self.page.set_content(fixture(name='其他课程'))
        with self.assertRaisesRegex(RuntimeError, '停止发布'):
            await video().add_required_product(self.page, timeout=5000)
        self.assertEqual(await self.page.evaluate('window.adds'), 0)

    async def test_missing_attachment_is_not_success(self):
        await self.page.set_content(fixture(attach=False))
        with self.assertRaisesRegex(RuntimeError, '停止发布'):
            await video().add_required_product(self.page, timeout=5000)
        self.assertEqual(await self.page.evaluate('window.adds'), 1)
        self.assertEqual(await self.page.evaluate('window.posts'), 0)

    async def test_disabled_course_is_not_forced(self):
        await self.page.set_content(fixture(disabled=True))
        with self.assertRaisesRegex(RuntimeError, '停止发布'):
            await video().add_required_product(self.page, timeout=5000)
        self.assertEqual(await self.page.evaluate('window.adds'), 0)


class TencentProductLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_product_budget_is_fifteen_minutes(self):
        self.assertEqual(PRODUCT_TIMEOUT_MS, 900000)
        self.assertEqual(inspect.signature(TencentVideo.add_required_product).parameters['timeout'].default,
                         PRODUCT_TIMEOUT_MS)

    async def test_shared_deadline_cancels_and_reports_current_step(self):
        uploader = video()
        cancelled = asyncio.Event()

        async def stalled(page, timeout):
            uploader.product_stage('选中指定商品')
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        uploader._add_required_product = stalled
        with self.assertRaisesRegex(RuntimeError, '选中指定商品'):
            await uploader.add_required_product(Mock(), timeout=50)
        self.assertTrue(cancelled.is_set())

    async def test_product_failure_prevents_immediate_and_scheduled_publication(self):
        for scheduled in (False, True):
            uploader = video(scheduled=scheduled)
            page = Mock(goto=AsyncMock(), wait_for_url=AsyncMock())
            page.locator.return_value.set_input_files = AsyncMock()
            for method in ('add_title_tags', 'set_location', 'add_collection', 'detect_upload_status',
                           'add_original', 'add_mark', 'set_schedule_time_tencent', 'add_short_title',
                           'click_publish'):
                setattr(uploader, method, AsyncMock())
            uploader.add_required_product = AsyncMock(side_effect=RuntimeError('商品未确认'))
            with self.assertRaisesRegex(RuntimeError, '商品未确认'):
                await uploader.publish_page(page)
            uploader.click_publish.assert_not_awaited()
            self.assertEqual(uploader.set_schedule_time_tencent.await_count, int(scheduled))

    async def test_product_failure_closes_task_browser_without_saving_cookie(self):
        uploader = video()
        uploader.publish_page = AsyncMock(side_effect=RuntimeError('商品未确认'))
        context = SimpleNamespace(new_page=AsyncMock(), close=AsyncMock(), storage_state=AsyncMock())
        browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())
        runtime = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
        with patch('uploader.tencent_uploader.main.set_init_script', AsyncMock(return_value=context)):
            with self.assertRaisesRegex(RuntimeError, '商品未确认'):
                await uploader.upload(runtime)
        context.storage_state.assert_not_awaited()
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()

    async def test_cleanup_errors_preserve_original_failure_and_cancellation(self):
        for failure in (RuntimeError('商品未确认'), asyncio.CancelledError()):
            with self.subTest(error=type(failure).__name__):
                uploader = video()
                uploader.publish_page = AsyncMock(side_effect=failure)
                context = SimpleNamespace(new_page=AsyncMock(), storage_state=AsyncMock(),
                                          close=AsyncMock(side_effect=TimeoutError()))
                browser = SimpleNamespace(new_context=AsyncMock(return_value=context),
                                          close=AsyncMock(side_effect=RuntimeError('close failed')))
                runtime = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
                with patch('uploader.tencent_uploader.main.set_init_script', AsyncMock(return_value=context)):
                    with self.assertRaises(type(failure)) as raised:
                        await uploader.upload(runtime)
                self.assertIs(raised.exception, failure)
                context.storage_state.assert_not_awaited()
                context.close.assert_awaited_once()
                browser.close.assert_awaited_once()

    async def test_cleanup_timeout_does_not_report_successful_post_as_failure(self):
        uploader = video()
        uploader.publish_page = AsyncMock()
        context = SimpleNamespace(new_page=AsyncMock(), storage_state=AsyncMock(),
                                  close=AsyncMock(side_effect=TimeoutError()))
        browser = SimpleNamespace(new_context=AsyncMock(return_value=context),
                                  close=AsyncMock(side_effect=TimeoutError()))
        runtime = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
        with patch('uploader.tencent_uploader.main.set_init_script', AsyncMock(return_value=context)):
            await uploader.upload(runtime)
        uploader.publish_page.assert_awaited_once()
        context.storage_state.assert_awaited_once_with(path='unused.json')
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()

    async def test_each_cleanup_is_bounded_and_browser_close_is_still_attempted(self):
        cancelled = []

        async def stalled_close(name):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(name)

        async def close_context():
            await stalled_close('context')

        async def close_browser():
            await stalled_close('browser')

        await asyncio.wait_for(video().close_publish_browser(
            SimpleNamespace(close=close_context), SimpleNamespace(close=close_browser), timeout=0.01),
            timeout=1)
        self.assertEqual(cancelled, ['context', 'browser'])

    async def test_context_creation_error_survives_browser_cleanup_failure(self):
        failure = RuntimeError('context creation failed')
        browser = SimpleNamespace(new_context=AsyncMock(side_effect=failure),
                                  close=AsyncMock(side_effect=TimeoutError()))
        runtime = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
        with self.assertRaises(RuntimeError) as raised:
            await video().upload(runtime)
        self.assertIs(raised.exception, failure)
        browser.close.assert_awaited_once()


class TencentAccountResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / 'accounts.db'
        initialize(self.database)
        with connect(self.database) as connection:
            connection.executemany('INSERT INTO user_info(type,filePath,userName) VALUES(?,?,?)', [
                (2, 'random.json', '老陆本人'), (2, '老陆.json', '其他账号'),
                (3, 'random.json', '抖音账号'),
            ])

    def tearDown(self):
        self.temp.cleanup()

    def test_each_account_uses_its_database_name_not_filename(self):
        with patch.object(postVideo.conf, 'DATABASE_PATH', self.database), \
             patch.object(postVideo, 'TencentVideo') as publisher, \
             patch.object(postVideo.asyncio, 'run'):
            postVideo.post_video_tencent('老陆 title', ['a.mp4', 'b.mp4'], [], ['random.json', '老陆.json'])
        self.assertEqual([call.kwargs['account_name'] for call in publisher.call_args_list],
                         ['老陆本人', '其他账号', '老陆本人', '其他账号'])

    def test_active_app_database_takes_precedence(self):
        app = Flask(__name__)
        app.config['DATABASE_PATH'] = self.database
        app.config['COOKIES_FOLDER'] = Path(self.temp.name) / 'cookies'
        app.config['VIDEO_FOLDER'] = Path(self.temp.name) / 'videos'
        with app.app_context(), patch.object(postVideo.conf, 'DATABASE_PATH', '/missing/database'):
            self.assertEqual(postVideo._tencent_account_names(['random.json']), {'random.json': '老陆本人'})
            with patch.object(postVideo, 'TencentVideo') as publisher, patch.object(postVideo.asyncio, 'run'):
                postVideo.post_video_tencent('title', ['a.mp4'], [], ['random.json'])
            self.assertEqual(publisher.call_args.args[4], app.config['COOKIES_FOLDER'] / 'random.json')
            self.assertEqual(publisher.call_args.args[1], str(app.config['VIDEO_FOLDER'] / 'a.mp4'))

    def test_unknown_account_stops_before_browser_start(self):
        with patch.object(postVideo.conf, 'DATABASE_PATH', self.database), \
             patch.object(postVideo, 'TencentVideo') as publisher:
            with self.assertRaisesRegex(ValueError, '账号名称'):
                postVideo.post_video_tencent('title', ['a.mp4'], [], ['missing.json'])
        publisher.assert_not_called()

    def test_ambiguous_names_are_rejected(self):
        with connect(self.database) as connection:
            connection.execute('INSERT INTO user_info(type,filePath,userName) VALUES(2,?,?)',
                               ('random.json', '其他账号'))
        with patch.object(postVideo.conf, 'DATABASE_PATH', self.database):
            with self.assertRaisesRegex(ValueError, '账号名称'):
                postVideo._tencent_account_names(['random.json'])
