"""Exercise upload controls against real DOMs, including localized pages."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright

from uploader.tk_uploader.main import TiktokVideo
from uploader.web_publishers import InstagramWebVideo
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
