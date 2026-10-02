"""Exercise upload controls against real DOMs, including localized pages."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright

from uploader.tk_uploader.main import TiktokVideo
from uploader.web_publishers import InstagramWebVideo
from uploader.youtube_uploader.main import YouTubeVideo
from uploader.xiaohongshu_uploader.main import XiaoHongShuVideo
from utils.browser_runtime import chromium_launch_options


class PublishFormTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runtime = await async_playwright().start()
        self.browser = await self.runtime.chromium.launch(**chromium_launch_options(True))
        self.page = await self.browser.new_page()

    async def asyncTearDown(self):
        await self.browser.close()
        await self.runtime.stop()

    async def test_instagram_opens_composer_and_ignores_avatar_input(self):
        html = '''<button onclick="this.remove()">以后再说</button>
            <input type="file" accept="image/jpeg">
            <button onclick="document.querySelector('#composer').innerHTML =
                '&lt;input type=file accept=video/mp4&gt;'">
                <svg aria-label="新帖子" width="24" height="24"></svg>
            </button><div id="composer" role="dialog"></div>'''
        await self.page.route("**/*", lambda route: route.fulfill(body=html, content_type="text/html; charset=utf-8"))
        uploader = InstagramWebVideo("title", "unused", [], "unused")
        file_input = await uploader.open_composer(self.page)
        self.assertEqual(self.page.url, "https://www.instagram.com/")
        self.assertEqual(await file_input.get_attribute("accept"), "video/mp4")

    async def test_tiktok_continues_after_navigation_timeout_with_ready_chinese_form(self):
        await self.page.set_content('''<input type="file" accept="video/*">
            <button>选择视频</button><button>发布</button>
            <div contenteditable="true" role="textbox">old title</div>''')
        wrapper = SimpleNamespace(
            goto=AsyncMock(side_effect=PlaywrightTimeoutError("slow resource")),
            url="https://www.tiktok.com/tiktokstudio/upload",
            frames=self.page.frames,
        )
        uploader = TiktokVideo("new title", "unused", [], 0, "unused")
        file_input = await uploader.open_upload_page(wrapper)
        self.assertEqual(await file_input.get_attribute("accept"), "video/*")
        await uploader.add_title_tags(self.page)
        self.assertIn("new title", await self.page.get_by_role("textbox").inner_text())
        self.assertNotIn("old title", await self.page.get_by_role("textbox").inner_text())
        self.assertEqual(await uploader.publish_button().inner_text(), "发布")

    async def test_tiktok_finds_video_input_inside_iframe(self):
        await self.page.set_content('''<iframe srcdoc='<input type="file" accept="video/mp4">'></iframe>''')
        wrapper = SimpleNamespace(goto=AsyncMock(), url="https://www.tiktok.com/tiktokstudio/upload", frames=self.page.frames)
        uploader = TiktokVideo("title", "unused", [], 0, "unused")
        file_input = await uploader.open_upload_page(wrapper)
        self.assertEqual(await file_input.get_attribute("accept"), "video/mp4")

    async def test_instagram_reels_notice_and_chinese_continue_steps(self):
        await self.page.set_content('''
            <div role="dialog">视频帖现在会以 Reels 的形式分享
              <button onclick="this.parentElement.remove()">确定</button></div>
            <div id="crop" role="dialog"><button onclick="this.parentElement.remove();
              document.querySelector('#edit').hidden=false">继续</button></div>
            <div id="edit" role="dialog" hidden><button onclick="this.parentElement.remove();
              document.querySelector('#caption').hidden=false">继续</button></div>
            <div id="caption" role="dialog" hidden>
              <div role="textbox" contenteditable="true"></div></div>''')
        uploader = InstagramWebVideo("Title", "unused", ["tag"], "unused")
        editor = await uploader.prepare_caption(self.page)
        self.assertEqual((await editor.inner_text()).split(), ["Title", "#tag"])

    async def test_youtube_confirms_matching_public_row_after_completion_dialog(self):
        await self.page.set_content('''
            <a href="https://youtube.com/shorts/abc123">视频链接</a>
            <button id="done-button" onclick="this.disabled=true;
              document.querySelector('#result').hidden=false">发布</button>
            <div id="result" role="dialog" hidden>视频已发布
              <button onclick="this.parentElement.remove();
                document.querySelector('#row').hidden=false">关闭</button></div>
            <div role="row" id="row" hidden>
              <a href="https://studio.youtube.com/video/abc123/edit">Title</a>
              <span>公开</span></div>''')
        uploader = YouTubeVideo("Title", "unused", [], "unused")
        self.assertTrue(callable(getattr(uploader, "publish_and_confirm", None)),
                        "YouTube lacks final-result verification")
        url = await uploader.publish_and_confirm(self.page, timeout=1500)
        self.assertEqual(url, "https://youtube.com/shorts/abc123")
        self.assertEqual(await self.page.get_by_role("dialog").count(), 0)

    async def test_youtube_does_not_accept_private_row_for_public_request(self):
        await self.page.set_content('''
            <a href="https://youtu.be/abc123">视频链接</a>
            <button id="done-button">发布</button>
            <div role="row"><a href="/video/abc123/edit">Title</a><span>私享</span></div>''')
        uploader = YouTubeVideo("Title", "unused", [], "unused")
        self.assertTrue(callable(getattr(uploader, "publish_and_confirm", None)),
                        "YouTube lacks final-result verification")
        with self.assertRaisesRegex(TimeoutError, "未确认"):
            await uploader.publish_and_confirm(self.page, timeout=400)

    async def test_xhs_clicks_non_button_publish_control_once(self):
        await self.page.route("https://creator.xiaohongshu.com/**", lambda route:
                              route.fulfill(body="发布成功"))
        await self.page.set_content('''<button>发布笔记</button>
            <div class="ProseMirror" contenteditable="true">#自动发布</div>
            <div onclick="location.href='https://creator.xiaohongshu.com/publish/success'">发布</div>''')
        uploader = XiaoHongShuVideo("Title", "unused", [], None, "unused")
        self.assertTrue(callable(getattr(uploader, "submit_and_confirm", None)),
                        "XHS requires semantic publish selection and bounded confirmation")
        await uploader.submit_and_confirm(self.page, timeout=1500)
        self.assertIn("/publish/success", self.page.url)

    async def test_xhs_unconfirmed_submission_is_not_repeated(self):
        await self.page.set_content('''<div id="count">0</div>
            <div onclick="let c=document.querySelector('#count'); c.textContent=+c.textContent+1">发布</div>''')
        uploader = XiaoHongShuVideo("Title", "unused", [], None, "unused")
        self.assertTrue(callable(getattr(uploader, "submit_and_confirm", None)))
        with self.assertRaisesRegex(Exception, "未确认"):
            await uploader.submit_and_confirm(self.page, timeout=400)
        self.assertEqual(await self.page.locator("#count").inner_text(), "1")

    async def test_xhs_waits_for_upload_without_visible_file_input(self):
        await self.page.set_content('''<input class="upload-input" type="file" hidden>
            <span class="video-plugin-title-action">重新上传</span>''')
        uploader = XiaoHongShuVideo("Title", "unused", [], None, "unused")
        self.assertTrue(callable(getattr(uploader, "wait_video_ready", None)))
        await uploader.wait_video_ready(self.page, timeout=400)

    async def test_xhs_publishes_through_closed_shadow_button_after_enabled(self):
        await self.page.route("https://creator.xiaohongshu.com/**", lambda route:
                              route.fulfill(body="发布成功"))
        await self.page.set_content('''<xhs-publish-btn submit-text="发布"></xhs-publish-btn>
            <script>const root=document.querySelector('xhs-publish-btn').attachShadow({mode:'closed'});
              root.innerHTML='<button>暂存离开</button><button disabled aria-disabled="true">发布</button>';
              const publish=root.querySelectorAll('button')[1];
              publish.onclick=()=>location.href='https://creator.xiaohongshu.com/publish/success';
              setTimeout(()=>{publish.disabled=false;publish.setAttribute('aria-disabled','false')},200);
            </script>''')
        uploader = XiaoHongShuVideo("Title", "unused", [], None, "unused")
        await uploader.submit_and_confirm(self.page, timeout=2000)
        self.assertIn('/publish/success', self.page.url)

    async def test_xhs_does_not_click_disabled_shadow_button(self):
        await self.page.set_content('''<xhs-publish-btn submit-text="发布"></xhs-publish-btn>
            <script>const root=document.querySelector('xhs-publish-btn').attachShadow({mode:'closed'});
              root.innerHTML='<button disabled aria-disabled="true">发布</button>';
              window.clicks=0;root.querySelector('button').onclick=()=>window.clicks++;</script>''')
        uploader = XiaoHongShuVideo("Title", "unused", [], None, "unused")
        with self.assertRaisesRegex(TimeoutError, '不可用'):
            await uploader.submit_and_confirm(self.page, timeout=400)
        self.assertEqual(await self.page.evaluate('window.clicks'), 0)
