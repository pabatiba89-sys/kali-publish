import tempfile
import unittest
from pathlib import Path
from queue import Queue
from unittest.mock import AsyncMock, MagicMock, patch

from myUtils import login
from uploader.tk_uploader import main as tiktok


class FakeChromium:
    def __init__(self):
        self.storage_state = None

    async def launch_persistent_context(self, user_data_dir, **_options):
        raise AssertionError("exported profile state must not reopen the login profile")

    async def launch(self, **_options):
        return self

    async def new_context(self, storage_state):
        self.storage_state = Path(storage_state)
        return "storage-state-context"


class FakePlaywright:
    def __init__(self):
        self.chromium = FakeChromium()


class TikTokLoginTests(unittest.IsolatedAsyncioTestCase):
    async def test_regular_chrome_login_uses_dedicated_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "tiktok-profile"
            process = MagicMock()
            process.poll.return_value = None
            save_state = AsyncMock(return_value=True)

            with (
                patch.object(tiktok, "resolve_chrome_executable", return_value=Path("/chrome")),
                patch.object(tiktok.subprocess, "Popen", return_value=process) as popen,
                patch.object(tiktok, "chrome_profile_has_cookies", return_value=True),
                patch.object(tiktok, "reserve_loopback_port", return_value=43210),
                patch.object(tiktok, "save_chrome_storage_state", save_state),
                patch.object(tiktok, "_stop_chrome_process"),
                patch.object(tiktok.asyncio, "sleep", return_value=None),
            ):
                result = await tiktok.tiktok_cookie_gen(profile)

            self.assertTrue(result["success"])
            command = popen.call_args.args[0]
            self.assertIn(f"--user-data-dir={profile}", command)
            self.assertIn("--profile-directory=Default", command)
            self.assertIn("--remote-debugging-port=43210", command)
            self.assertIn("--remote-debugging-address=127.0.0.1", command)
            save_state.assert_awaited_once_with(
                43210, profile / "storage-state.json"
            )

    async def test_publish_context_uses_exported_profile_state(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "tiktok-profile"
            profile.mkdir()
            state = profile / "storage-state.json"
            state.write_text("{}", encoding="utf-8")
            playwright = FakePlaywright()

            context, browser = await tiktok._open_account_context(
                playwright, profile, headless=True
            )

            self.assertEqual(context, "storage-state-context")
            self.assertIs(browser, playwright.chromium)
            self.assertEqual(playwright.chromium.storage_state, state)

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
