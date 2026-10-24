"""Offline browser regression tests for Instagram crop/edit transitions."""
import unittest
from unittest.mock import AsyncMock, patch

from playwright.async_api import async_playwright

from uploader.web_publishers import InstagramWebVideo
from utils.browser_runtime import chromium_launch_options


class InstagramCropTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runtime = await async_playwright().start()
        self.browser = await self.runtime.chromium.launch(**chromium_launch_options(True))
        self.page = await self.browser.new_page()
        await self.page.route('**/*', lambda route: route.abort())
        self.uploader = InstagramWebVideo('Test caption', 'unused', [], 'unused')

    async def asyncTearDown(self):
        await self.browser.close()
        await self.runtime.stop()

    async def test_slow_transition_with_reused_next_button_clicks_each_stage_once(self):
        await self.page.set_content('''<div role="dialog"><h2 id="stage">Crop</h2>
          <button onclick="advance()">Next</button><textarea hidden></textarea></div>
          <script>window.clicks=[];function advance(){
            let stage=document.querySelector('#stage').textContent;window.clicks.push(stage);
            setTimeout(()=>{if(stage==='Crop'){document.querySelector('#stage').textContent='Edit';}
            else{document.querySelector('button').hidden=true;document.querySelector('textarea').hidden=false;}},600);
          }</script>''')
        caption = await self.uploader.prepare_caption(self.page, timeout=5000)
        self.assertEqual(await caption.input_value(), 'Test caption')
        self.assertEqual(await self.page.evaluate('window.clicks'), ['Crop', 'Edit'])

    async def test_ignores_background_hidden_and_disabled_controls(self):
        await self.page.set_content('''<textarea id="background"></textarea>
          <button onclick="window.wrong++">Next</button><div role="dialog">
          <h2>裁剪</h2><button hidden onclick="window.wrong++">下一步</button>
          <button disabled onclick="window.wrong++">下一步</button>
          <div aria-disabled="true"><button onclick="window.wrong++">下一步</button></div>
          <button onclick="window.right++;this.hidden=true;document.querySelector('#caption').hidden=false">下一步</button>
          <textarea id="caption" hidden></textarea></div>
          <script>window.wrong=0;window.right=0</script>''')
        await self.uploader.prepare_caption(self.page, timeout=3000)
        self.assertEqual(await self.page.evaluate('[window.right,window.wrong]'), [1, 0])
        self.assertEqual(await self.page.locator('#background').input_value(), '')

    async def test_waits_for_aria_disabled_ancestor_then_clicks_role_button(self):
        await self.page.set_content('''<div role="dialog"><h2>裁切</h2>
          <div id="wrapper" aria-disabled="true"><div role="button" tabindex="0"
            onclick="window.clicks++;this.hidden=true;document.querySelector('textarea').hidden=false">繼續</div></div>
          <textarea hidden></textarea></div><script>window.clicks=0;
          setTimeout(()=>document.querySelector('#wrapper').removeAttribute('aria-disabled'),500)</script>''')
        await self.uploader.prepare_caption(self.page, timeout=3000)
        self.assertEqual(await self.page.evaluate('window.clicks'), 1)

    async def test_headerless_link_moves_directly_to_caption(self):
        await self.page.set_content('''<div role="dialog"><a href="#" onclick="event.preventDefault();
          this.remove();document.querySelector('textarea').hidden=false">Continue</a>
          <textarea hidden></textarea></div>''')
        caption = await self.uploader.prepare_caption(self.page, timeout=3000)
        self.assertEqual(await caption.input_value(), 'Test caption')

    async def test_caption_already_visible_does_not_click_next(self):
        await self.page.set_content('''<div role="dialog"><button onclick="window.clicks++">Next</button>
          <div contenteditable="true" role="textbox"></div></div><script>window.clicks=0</script>''')
        caption = await self.uploader.prepare_caption(self.page, timeout=3000)
        self.assertEqual(await caption.inner_text(), 'Test caption')
        self.assertEqual(await self.page.evaluate('window.clicks'), 0)

    async def test_stuck_crop_never_double_clicks_or_shares(self):
        for heading in ('<h2>Crop</h2>', ''):
            await self.page.set_content(f'''<div role="dialog">{heading}
              <button onclick="window.nexts++">Next</button>
              <button onclick="window.shares++">Share</button></div>
              <script>window.nexts=0;window.shares=0</script>''')
            with self.assertRaisesRegex(TimeoutError, '未点击分享'):
                await self.uploader.prepare_caption(self.page, timeout=800)
            self.assertEqual(await self.page.evaluate('[window.nexts,window.shares]'), [1, 0])

    async def test_disabled_next_never_clicked(self):
        await self.page.set_content('''<div role="dialog"><h2>Crop</h2>
          <button disabled onclick="window.clicks++">Next</button></div><script>window.clicks=0</script>''')
        with self.assertRaises(TimeoutError):
            await self.uploader.prepare_caption(self.page, timeout=500)
        self.assertEqual(await self.page.evaluate('window.clicks'), 0)

    async def test_reels_notice_overlay_is_dismissed_before_crop(self):
        await self.page.set_content('''<div role="dialog"><h2>Crop</h2>
          <button onclick="window.nexts++;this.remove();document.querySelector('textarea').hidden=false">Next</button>
          <textarea hidden></textarea></div><div role="dialog">Video posts are now shared as reels
          <button onclick="window.notices++;this.parentElement.remove()">Got it</button></div>
          <script>window.nexts=0;window.notices=0</script>''')
        await self.uploader.prepare_caption(self.page, timeout=3000)
        self.assertEqual(await self.page.evaluate('[window.nexts,window.notices]'), [1, 1])

    async def test_crop_to_share_flow_completes_without_manual_clicks(self):
        self.uploader = InstagramWebVideo('视频标题', 'unused', ['AI', '#喀理系统'], 'unused',
                                          description='视频正文')
        await self.page.set_content('''<input type="file" accept="video/mp4">
          <div role="dialog"><h2 id="stage">裁剪</h2><button id="next" onclick="advance()">下一步</button>
          <textarea hidden></textarea><button id="share" hidden onclick="window.shares++;
            window.caption=document.querySelector('textarea').value;
            this.parentElement.innerHTML='<h2>你的 Reels 已分享。</h2>'">分享</button></div>
          <script>window.nexts=0;window.shares=0;function advance(){window.nexts++;
            setTimeout(()=>{if(window.nexts===1){document.querySelector('#stage').textContent='编辑';}
            else{document.querySelector('#next').hidden=true;document.querySelector('textarea').hidden=false;
            document.querySelector('#share').hidden=false;}},400);}</script>''')
        self.uploader.file_path = {'name': 'fixture.mp4', 'mimeType': 'video/mp4', 'buffer': b'fixture'}
        with patch.object(self.uploader, 'open_composer', AsyncMock(return_value=self.page.locator('input'))):
            import asyncio
            await asyncio.wait_for(self.uploader.publish(self.page), timeout=5)
        self.assertEqual(await self.page.evaluate('[window.nexts,window.shares,window.caption]'),
                         [2, 1, '视频标题\n\n视频正文\n\n#AI #喀理系统'])

    async def test_share_waits_for_enabled_control_and_ignores_background(self):
        await self.page.set_content('''<button onclick="window.wrong++">分享</button>
          <div role="dialog" hidden><button onclick="window.wrong++">分享</button></div>
          <div role="dialog"><textarea></textarea><button disabled>分享</button>
          <button id="submit" disabled onclick="window.shares++;window.caption=document.querySelector('textarea').value">分享</button>
          </div><script>window.wrong=0;window.shares=0;
          setTimeout(()=>document.querySelector('#submit').disabled=false,600)</script>''')
        self.uploader = InstagramWebVideo('标题', 'unused', [' #AI ', '#创作'], 'unused')
        caption = await self.uploader.prepare_caption(self.page, timeout=3000)
        await self.uploader.submit_caption(caption, timeout=3000)
        self.assertEqual(await self.page.evaluate('[window.wrong,window.shares,window.caption]'),
                         [0, 1, '标题\n\n#AI #创作'])

    async def test_contenteditable_caption_and_role_share_button(self):
        await self.page.set_content('''<div role="dialog"><div role="textbox" contenteditable="true"></div>
          <div role="button" tabindex="0" onclick="window.caption=document.querySelector('[role=textbox]').innerText;
          window.shares++">Share</div></div><script>window.shares=0</script>''')
        self.uploader = InstagramWebVideo('Title', 'unused', ['topic'], 'unused', description='Body')
        caption = await self.uploader.prepare_caption(self.page, timeout=3000)
        await self.uploader.submit_caption(caption, timeout=3000)
        self.assertEqual(await self.page.evaluate('window.shares'), 1)
        self.assertEqual((await self.page.evaluate('window.caption')).split(), ['Title', 'Body', '#topic'])

    async def test_reverted_caption_prevents_share(self):
        await self.page.set_content('''<div role="dialog"><textarea onblur="this.value='' "></textarea>
          <button onclick="window.shares++">分享</button></div><script>window.shares=0</script>''')
        caption = await self.uploader.prepare_caption(self.page, timeout=3000)
        with self.assertRaisesRegex(RuntimeError, '未点击分享'):
            await self.uploader.submit_caption(caption, timeout=3000)
        self.assertEqual(await self.page.evaluate('window.shares'), 0)

    async def test_long_caption_is_rejected_before_upload_not_truncated(self):
        self.uploader = InstagramWebVideo('x' * 2200, 'unused', ['topic'], 'unused')
        with patch.object(self.uploader, 'open_composer', AsyncMock()) as open_composer:
            with self.assertRaisesRegex(ValueError, '2200'):
                await self.uploader.publish(self.page)
        open_composer.assert_not_awaited()

    async def test_share_without_success_is_not_retried(self):
        await self.page.set_content('''<input type="file"><div role="dialog"><textarea></textarea>
          <button onclick="window.shares++">分享</button></div><script>window.shares=0</script>''')
        self.uploader.file_path = {'name': 'fixture.mp4', 'mimeType': 'video/mp4', 'buffer': b'fixture'}
        wait_result = self.uploader.wait_share_result
        async def bounded_result(page):
            return await wait_result(page, timeout=500)
        with patch.object(self.uploader, 'open_composer', AsyncMock(return_value=self.page.locator('input'))), \
             patch.object(self.uploader, 'wait_share_result', side_effect=bounded_result):
            with self.assertRaises(TimeoutError):
                await self.uploader.publish(self.page)
        self.assertEqual(await self.page.evaluate('window.shares'), 1)


if __name__ == '__main__':
    unittest.main()
