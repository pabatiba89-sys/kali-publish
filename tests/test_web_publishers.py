import unittest

from uploader.web_publishers import BrowserVideoPublisher, WEB_PLATFORMS, _config, _has_login_cookies


class FakeContext:
    def __init__(self, cookie_names):
        self.cookie_names = cookie_names

    async def cookies(self):
        return [{"name": name} for name in self.cookie_names]


class BrowserPublisherTests(unittest.IsolatedAsyncioTestCase):
    async def test_required_login_cookies_are_detected(self):
        self.assertTrue(await _has_login_cookies(FakeContext({"c_user", "xs"}), {"c_user", "xs"}))
        self.assertFalse(await _has_login_cookies(FakeContext({"c_user"}), {"c_user", "xs"}))

    async def test_all_web_platforms_have_login_configuration(self):
        self.assertEqual(set(WEB_PLATFORMS), {7, 8, 9})
        self.assertEqual(_config(7)["name"], "X")
        with self.assertRaisesRegex(ValueError, "Unsupported browser platform"):
            _config(10)

    async def test_caption_normalizes_hash_tags(self):
        publisher = BrowserVideoPublisher("Title", "video.mp4", ["#one", "two"], "account.json")
        self.assertEqual(publisher.caption, "Title\n\n#one #two")


if __name__ == "__main__":
    unittest.main()
