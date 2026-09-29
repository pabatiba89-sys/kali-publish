import unittest
import tempfile
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


if __name__ == "__main__":
    unittest.main()
