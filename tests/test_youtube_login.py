import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from uploader.youtube_uploader import main as youtube


class YouTubeLoginTests(unittest.TestCase):
    def test_detects_completed_login_from_chrome_history(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = Path(temporary_directory)
            default = profile / "Default"
            default.mkdir()
            with closing(sqlite3.connect(default / "History")) as connection:
                connection.execute(
                    "CREATE TABLE urls (url TEXT NOT NULL, last_visit_time INTEGER NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO urls (url, last_visit_time) VALUES (?, ?)",
                    ("https://studio.youtube.com/channel/UC-test", 1),
                )
                connection.commit()

            self.assertEqual(
                youtube._studio_channel_from_history(profile),
                "https://studio.youtube.com/channel/UC-test",
            )

    def test_ignores_google_sign_in_history(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = Path(temporary_directory)
            default = profile / "Default"
            default.mkdir()
            with closing(sqlite3.connect(default / "History")) as connection:
                connection.execute(
                    "CREATE TABLE urls (url TEXT NOT NULL, last_visit_time INTEGER NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO urls (url, last_visit_time) VALUES (?, ?)",
                    ("https://accounts.google.com/signin", 1),
                )
                connection.commit()

            self.assertEqual(youtube._studio_channel_from_history(profile), "")


class FakeChromium:
    def __init__(self):
        self.storage_state = None

    async def launch(self, **_options):
        return self

    async def new_context(self, storage_state):
        self.storage_state = Path(storage_state)
        return "storage-state-context"

    async def launch_persistent_context(self, **_kwargs):
        raise AssertionError("exported profile state must not reopen the login profile")


class FakePlaywright:
    def __init__(self):
        self.chromium = FakeChromium()


class YouTubeProfileStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_context_uses_exported_profile_state(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = Path(temporary_directory) / "youtube-profile"
            profile.mkdir()
            state = profile / "storage-state.json"
            state.write_text("{}", encoding="utf-8")
            playwright = FakePlaywright()

            context, browser = await youtube._open_account_context(
                playwright, profile, headless=True
            )

            self.assertEqual(context, "storage-state-context")
            self.assertIs(browser, playwright.chromium)
            self.assertEqual(playwright.chromium.storage_state, state)


if __name__ == "__main__":
    unittest.main()
