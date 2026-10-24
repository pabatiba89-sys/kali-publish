"""Offline browser fixtures for the explicitly approved checks-pending warning."""
import unittest

from playwright.async_api import async_playwright

from uploader.youtube_uploader.main import YouTubeVideo
from utils.browser_runtime import chromium_launch_options


WARNING = '''<div id="warning" role="dialog">
    <h2>我们仍在检查你的内容</h2>
    <p>在我们完成检查之前，建议你将内容保持为私享。如果现在发布，你可能会收到警示。</p>
    <button id="confirm" onclick="window.confirms++">仍然发布</button>
    <button onclick="window.backs++">返回</button></div>'''


class YouTubePublishTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runtime = await async_playwright().start()
        self.browser = await self.runtime.chromium.launch(**chromium_launch_options(True))
        self.page = await self.browser.new_page()
        await self.page.route('**/*', lambda route: route.fulfill(body=''))
        self.uploader = YouTubeVideo('title', 'unused', [], 'unused')

    async def asyncTearDown(self):
        await self.browser.close()
        await self.runtime.stop()

    async def fixture(self, html=WARNING):
        await self.page.set_content('<script>window.confirms=0;window.posts=0;window.backs=0</script>' + html)

    async def test_delayed_warning_then_matching_public_result(self):
        await self.fixture(WARNING.replace('id="warning"', 'id="warning" hidden') + '''
            <a href="https://youtube.com/shorts/abc123">视频链接</a>
            <button id="done-button" onclick="window.posts++;
              setTimeout(()=>document.querySelector('#warning').hidden=false,200)">发布</button>
            <div id="result" role="dialog" hidden>视频已发布
              <button onclick="this.parentElement.remove();document.querySelector('#row').hidden=false">关闭</button></div>
            <div id="row" role="row" hidden><a href="/video/abc123/edit">title</a><span>公开</span></div>''')
        await self.page.locator('#confirm').evaluate('''button => button.addEventListener('click', () => {
            document.querySelector('#warning').remove();
            setTimeout(()=>document.querySelector('#result').hidden=false,300);
        })''')
        self.assertEqual(await self.uploader.publish_and_confirm(self.page, timeout=5000),
                         'https://youtube.com/shorts/abc123')
        self.assertEqual(await self.page.evaluate('[window.posts,window.confirms,window.backs]'), [1, 1, 0])

    async def test_confirmation_alone_is_not_success_and_not_repeated(self):
        await self.fixture()
        with self.assertRaisesRegex(TimeoutError, '未确认'):
            await self.uploader.confirm_publication(self.page, 'abc123', timeout=700)
        self.assertEqual(await self.page.evaluate('window.confirms'), 1)

    async def test_disappearing_warning_does_not_prove_success(self):
        await self.fixture()
        await self.page.locator('#confirm').evaluate(
            "button=>button.addEventListener('click',()=>document.querySelector('#warning').remove())")
        with self.assertRaises(TimeoutError):
            await self.uploader.confirm_publication(self.page, 'abc123', timeout=500)
        self.assertEqual(await self.page.evaluate('window.confirms'), 1)

    async def test_hidden_disabled_and_unrelated_warnings_are_not_accepted(self):
        variants = [
            WARNING.replace('id="warning"', 'id="warning" hidden'),
            WARNING.replace('id="confirm"', 'id="confirm" disabled'),
            WARNING.replace('id="confirm"', 'id="confirm" aria-disabled="true"'),
            WARNING.replace('我们仍在检查你的内容', '发现版权问题'),
            WARNING.replace('在我们完成检查之前，建议你将内容保持为私享。如果现在发布，你可能会收到警示。', '请处理版权违规。'),
            WARNING.replace('仍然发布', '删除视频'),
        ]
        for html in variants:
            with self.subTest(html=html):
                await self.fixture(html)
                self.assertFalse(await self.uploader.confirm_pending_checks(self.page))
                self.assertEqual(await self.page.evaluate('window.confirms'), 0)

    async def test_warning_outside_dialog_and_background_button_are_ignored(self):
        await self.fixture(WARNING.replace('role="dialog"', '') + '<button>仍然发布</button>')
        self.assertFalse(await self.uploader.confirm_pending_checks(self.page))
        self.assertEqual(await self.page.evaluate('window.confirms'), 0)

    async def test_non_public_request_never_uses_public_warning_confirmation(self):
        for visibility in ('private', 'unlisted'):
            await self.fixture()
            self.uploader.visibility = visibility
            self.assertFalse(await self.uploader.confirm_pending_checks(self.page))
            self.assertEqual(await self.page.evaluate('window.confirms'), 0)

    async def test_wrong_video_or_private_result_is_not_success(self):
        for video_id, visibility in (('different', '公开'), ('abc123', '私享')):
            await self.fixture(WARNING + f'<div role="row"><a href="/video/{video_id}/edit">title</a>'
                               f'<span>{visibility}</span></div>')
            with self.assertRaises(TimeoutError):
                await self.uploader.confirm_publication(self.page, 'abc123', timeout=500)
            self.assertEqual(await self.page.evaluate('window.confirms'), 1)

    async def test_english_warning_is_scoped_and_confirmed(self):
        await self.fixture(WARNING.replace('我们仍在检查你的内容', "We're still checking your content")
                           .replace('在我们完成检查之前，建议你将内容保持为私享。如果现在发布，你可能会收到警示。',
                                    'We recommend keeping your video private until checks finish.')
                           .replace('仍然发布', 'Publish anyway'))
        self.assertTrue(await self.uploader.confirm_pending_checks(self.page))
        self.assertEqual(await self.page.evaluate('window.confirms'), 1)
