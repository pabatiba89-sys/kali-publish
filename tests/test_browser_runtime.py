import unittest
from unittest.mock import patch

from utils import browser_runtime


class BrowserRuntimeTests(unittest.TestCase):
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
