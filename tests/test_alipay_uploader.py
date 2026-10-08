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
