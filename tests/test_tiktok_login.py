import tempfile
import unittest
from pathlib import Path
from queue import Queue
from unittest.mock import MagicMock, patch

from myUtils import login
from uploader.tk_uploader import main as tiktok


class FakeChromium:
    def __init__(self):
        self.persistent_profile = None

    async def launch_persistent_context(self, user_data_dir, **_options):
        self.persistent_profile = Path(user_data_dir)
        return "persistent-context"

    async def launch(self, **_options):
        raise AssertionError("profile directory must not use storage-state browser launch")


class FakePlaywright:
    def __init__(self):
        self.chromium = FakeChromium()


class TikTokLoginTests(unittest.IsolatedAsyncioTestCase):
    async def test_regular_chrome_login_uses_dedicated_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "tiktok-profile"
            process = MagicMock()
            process.poll.return_value = None

            with (
                patch.object(tiktok, "resolve_chrome_executable", return_value=Path("/chrome")),
                patch.object(tiktok.subprocess, "Popen", return_value=process) as popen,
                patch.object(tiktok, "chrome_profile_has_cookies", return_value=True),
                patch.object(tiktok, "_stop_chrome_process"),
                patch.object(tiktok.asyncio, "sleep", return_value=None),
            ):
                result = await tiktok.tiktok_cookie_gen(profile)

            self.assertTrue(result["success"])
            command = popen.call_args.args[0]
            self.assertIn(f"--user-data-dir={profile}", command)
            self.assertIn("--profile-directory=Default", command)

    async def test_publish_context_reuses_regular_chrome_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "tiktok-profile"
            profile.mkdir()
            playwright = FakePlaywright()

            context, browser = await tiktok._open_account_context(
                playwright, profile, headless=True
            )

            self.assertEqual(context, "persistent-context")
            self.assertIsNone(browser)
            self.assertEqual(playwright.chromium.persistent_profile, profile)

    async def test_account_login_allocates_tiktok_profile_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            observed = []

            async def fake_cookie_gen(account_path):
                observed.append(Path(account_path))
                Path(account_path).mkdir()
                return {"success": True}

            with (
                patch.object(login, "COOKIES_FOLDER", Path(directory)),
                patch.object(login, "tiktok_browser_cookie_gen", fake_cookie_gen),
                patch.object(login, "_record_account") as record,
            ):
                await login.tiktok_cookie_gen("tiktok-account", Queue())

            self.assertTrue(observed[0].name.startswith("tiktok-"))
            self.assertEqual(observed[0].suffix, "")
            record.assert_called_once_with(5, observed[0].name, "tiktok-account")


if __name__ == "__main__":
    unittest.main()
