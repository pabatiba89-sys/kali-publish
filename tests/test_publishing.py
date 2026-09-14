import unittest
from unittest.mock import Mock, patch

import publishing


class PublishingDispatchTests(unittest.TestCase):
    def test_standard_platform_dispatch(self):
        publisher = Mock()
        platform = {"name": "小红书", "publisher": publisher, "login": True}
        payload = {
            "type": 1,
            "title": "title",
            "tags": ["tag"],
            "fileList": ["video.mp4"],
            "accountList": ["account.json"],
            "sendnow": "now",
        }
        with patch.dict(publishing.PLATFORMS, {1: platform}):
            publishing.publish_videos(payload)
        publisher.assert_called_once_with(
            "title", ["video.mp4"], ["tag"], ["account.json"], None, False, 1, None, 0, ""
        )

    def test_douyin_product_fields_are_preserved(self):
        publisher = Mock()
        platform = {"name": "抖音", "publisher": publisher, "login": True}
        payload = {
            "type": 3,
            "fileList": ["video.mp4"],
            "accountList": ["account.json"],
            "productLink": "https://example.com/product",
            "productTitle": "product",
            "endpublishTime": "2026-09-15 10:00:00",
        }
        with patch.dict(publishing.PLATFORMS, {3: platform}):
            publishing.publish_videos(payload)
        arguments = publisher.call_args.args
        self.assertEqual(arguments[-3:], ("https://example.com/product", "product", "2026-09-15 10:00:00"))


if __name__ == "__main__":
    unittest.main()
