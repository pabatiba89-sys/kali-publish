import sqlite3
import tempfile
import unittest
from pathlib import Path
from queue import Queue
from unittest.mock import patch

from myUtils import login
from uploader.web_publishers import (
    BrowserVideoPublisher,
    WEB_PLATFORMS,
    _browser_cookie_auth,
    _authenticated_url_from_history,
    _config,
    _has_login_cookies,
)


class FakeContext:
    def __init__(self, cookie_names):
        self.cookie_names = cookie_names

    async def cookies(self):
        return [{"name": name} for name in self.cookie_names]

    async def add_init_script(self, **_kwargs):
        return None

    async def new_page(self):
        return FakePage()

    async def close(self):
        return None


class FakePage:
    url = "https://x.com/home"

    async def goto(self, *_args, **_kwargs):
        return None

    async def wait_for_timeout(self, _milliseconds):
        return None


class FakeChromium:
    def __init__(self):
        self.persistent_profile = None

    async def launch_persistent_context(self, user_data_dir, **_options):
        self.persistent_profile = Path(user_data_dir)
        return FakeContext({"auth_token"})

    async def launch(self, **_options):
        raise AssertionError("profile directory must not use storage-state browser launch")


class FakePlaywright:
    def __init__(self):
        self.chromium = FakeChromium()


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

    async def test_caption_includes_description(self):
        publisher = BrowserVideoPublisher(
            "Title",
            "video.mp4",
            ["one"],
            "account.json",
            description="Description",
        )
        self.assertEqual(publisher.caption, "Title\n\nDescription\n\n#one")

    async def test_regular_chrome_history_detects_only_authenticated_url(self):
        with tempfile.TemporaryDirectory() as directory:
            default = Path(directory) / "Default"
            default.mkdir()
            history = default / "History"
            with sqlite3.connect(history) as connection:
                connection.execute(
                    "CREATE TABLE urls (url TEXT, last_visit_time INTEGER)"
                )
                connection.execute(
                    "INSERT INTO urls VALUES (?, ?)",
                    ("https://x.com/i/flow/login", 1),
                )
                connection.execute(
                    "INSERT INTO urls VALUES (?, ?)",
                    ("https://x.com/home", 2),
                )
            self.assertEqual(
                _authenticated_url_from_history(
                    Path(directory), ("https://x.com/home%",)
                ),
                "https://x.com/home",
            )

    async def test_web_login_allocates_regular_chrome_profile_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            observed = []

            async def fake_cookie_gen(platform_type, account_path):
                observed.append((platform_type, Path(account_path)))
                Path(account_path).mkdir()
                return {"success": True}

            with (
                patch.object(login, "COOKIES_FOLDER", Path(directory)),
                patch.object(login, "social_browser_cookie_gen", fake_cookie_gen),
                patch.object(login, "_record_account"),
            ):
                await login._web_platform_cookie_gen(7, "x-account", Queue())

            self.assertEqual(observed[0][0], 7)
            self.assertEqual(observed[0][1].suffix, "")
            self.assertTrue(observed[0][1].is_dir())

    async def test_web_cookie_auth_reuses_profile_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "web-7-profile"
            profile.mkdir()
            playwright = FakePlaywright()

            self.assertTrue(await _browser_cookie_auth(playwright, 7, profile))
            self.assertEqual(playwright.chromium.persistent_profile, profile)


if __name__ == "__main__":
    unittest.main()
