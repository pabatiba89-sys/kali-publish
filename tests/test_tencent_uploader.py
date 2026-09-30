import unittest
from unittest.mock import AsyncMock, Mock, call

from uploader.tencent_uploader.main import TencentVideo


class TencentUploaderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.video = TencentVideo(
            "title",
            "video.mp4",
            ["tag"],
            "",
            "account.json",
        )

    async def test_title_tags_include_project_tag_and_mention(self):
        page = Mock()
        editor = Mock()
        editor.click = AsyncMock()
        page.locator.return_value = editor
        page.keyboard = Mock()
        page.keyboard.type = AsyncMock()
        page.keyboard.press = AsyncMock()

        await self.video.add_title_tags(page)

        self.assertEqual(
            page.keyboard.type.await_args_list,
            [call("title"), call("#tag"), call("#喀理系统"), call("@岳同学AI")],
        )

    async def test_selects_second_content_mark_when_available(self):
        page = Mock()
        selector = Mock()
        selector.count = AsyncMock(return_value=1)
        selector.first = Mock()
        selector.first.click = AsyncMock()
        options = Mock()
        options.count = AsyncMock(return_value=2)
        second = Mock()
        second.click = AsyncMock()
        options.nth.return_value = second
        page.locator.side_effect = [selector, options]
        page.wait_for_timeout = AsyncMock()

        await self.video.add_mark(page)

        selector.first.click.assert_awaited_once()
        options.nth.assert_called_once_with(1)
        second.click.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
