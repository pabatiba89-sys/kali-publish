import unittest
import tempfile
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from utils import browser_runtime, log


class BrowserRuntimeTests(unittest.TestCase):
    def test_logger_creates_nested_data_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            data_dir = Path(temporary_directory) / "new" / "data"
            with patch.object(log, "BASE_DIR", data_dir), patch.object(log.logger, "add"):
                log.create_logger("test", "logs/test.log")
            self.assertTrue((data_dir / "logs").is_dir())

    def test_uses_installed_chrome_channel_by_default(self):
        with patch.object(browser_runtime, "LOCAL_CHROME_PATH", ""):
            options = browser_runtime.chromium_launch_options(headless=True)
        self.assertEqual(options, {"headless": True, "channel": "chrome"})

    def test_explicit_chrome_path_overrides_channel(self):
        with patch.object(browser_runtime, "LOCAL_CHROME_PATH", "/path/to/chrome"):
            options = browser_runtime.chromium_launch_options(False, ["--lang=zh-CN"])
        self.assertEqual(
            options,
            {
                "headless": False,
                "args": ["--lang=zh-CN"],
                "executable_path": "/path/to/chrome",
            },
        )

    def test_resolves_configured_regular_chrome(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            chrome = Path(temporary_directory) / "chrome"
            chrome.touch()
            with patch.object(browser_runtime, "LOCAL_CHROME_PATH", str(chrome)):
                self.assertEqual(browser_runtime.resolve_chrome_executable(), chrome.resolve())

    def test_detects_required_cookie_names_in_regular_chrome_profile(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = Path(temporary_directory)
            default = profile / "Default"
            default.mkdir()
            with closing(sqlite3.connect(default / "Cookies")) as connection:
                connection.execute("CREATE TABLE cookies (host_key TEXT, name TEXT)")
                connection.executemany(
                    "INSERT INTO cookies VALUES (?, ?)",
                    [
                        (".youtube.com", "LOGIN_INFO"),
                        (".youtube.com", "SAPISID"),
                    ],
                )
                connection.commit()

            detector = getattr(browser_runtime, "chrome_profile_has_cookies", None)
            self.assertIsNotNone(detector)
            self.assertTrue(
                detector(profile, ("youtube.com",), {"LOGIN_INFO", "SAPISID"})
            )

    def test_rejects_home_history_without_required_login_cookie(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = Path(temporary_directory)
            default = profile / "Default"
            default.mkdir()
            with closing(sqlite3.connect(default / "Cookies")) as connection:
                connection.execute("CREATE TABLE cookies (host_key TEXT, name TEXT)")
                connection.execute(
                    "INSERT INTO cookies VALUES (?, ?)", (".x.com", "guest_id")
                )
                connection.commit()
            with closing(sqlite3.connect(default / "History")) as connection:
                connection.execute(
                    "CREATE TABLE urls (url TEXT, last_visit_time INTEGER)"
                )
                connection.execute(
                    "INSERT INTO urls VALUES (?, ?)", ("https://x.com/home", 1)
                )
                connection.commit()

            detector = getattr(browser_runtime, "chrome_profile_has_cookies", None)
            self.assertIsNotNone(detector)
            self.assertFalse(detector(profile, ("x.com",), {"auth_token"}))


if __name__ == "__main__":
    unittest.main()
