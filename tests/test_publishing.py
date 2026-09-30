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

    def test_publish_defaults_to_immediate(self):
        publisher = Mock()
        platform = {
            "name": "X",
            "publisher": publisher,
            "login": False,
            "supportsSchedule": False,
        }
        payload = {"type": 7, "fileList": ["video.mp4"], "accountList": ["account.json"]}
        with patch.dict(publishing.PLATFORMS, {7: platform}):
            publishing.publish_videos(payload)
        self.assertFalse(publisher.call_args.args[5])

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

    def test_platform_without_native_schedule_is_rejected(self):
        payload = {
            "type": 7,
            "fileList": ["video.mp4"],
            "accountList": ["account.json"],
            "sendnow": "schedule",
            "endpublishTime": "2026-10-01 10:00:00",
        }
        with self.assertRaisesRegex(ValueError, "does not support scheduled publishing"):
            publishing.publish_videos(payload)

    def test_youtube_metadata_is_forwarded(self):
        publisher = Mock()
        platform = {
            "name": "YouTube",
            "publisher": publisher,
            "login": True,
            "supportsSchedule": False,
        }
        payload = {
            "type": 6,
            "fileList": ["video.mp4"],
            "accountList": ["account.json"],
            "description": "description",
            "thumbnailPath": "cover.png",
            "playlist": "series",
            "visibility": "unlisted",
        }
        with patch.dict(publishing.PLATFORMS, {6: platform}):
            publishing.publish_videos(payload)
        self.assertEqual(
            publisher.call_args.args[-5:],
            ("", "description", "cover.png", "series", "unlisted"),
        )

    def test_alipay_metadata_is_forwarded(self):
        publisher = Mock()
        platform = {
            "name": "支付宝生活号",
            "publisher": publisher,
            "login": True,
            "supportsSchedule": False,
        }
        payload = {
            "type": 10,
            "fileList": ["video.mp4"],
            "accountList": ["account.json"],
            "description": "description",
            "thumbnail": "cover.png",
            "collectionName": "series",
        }
        with patch.dict(publishing.PLATFORMS, {10: platform}):
            publishing.publish_videos(payload)
        self.assertEqual(
            publisher.call_args.args[-4:],
            ("", "description", "cover.png", "series"),
        )

    def test_tiktok_description_and_thumbnail_are_forwarded(self):
        publisher = Mock()
        platform = {
            "name": "TikTok",
            "publisher": publisher,
            "login": True,
            "supportsSchedule": True,
        }
        payload = {
            "type": 5,
            "fileList": ["video.mp4"],
            "accountList": ["account.json"],
            "description": "description",
            "thumbnailPath": "cover.png",
        }
        with patch.dict(publishing.PLATFORMS, {5: platform}):
            publishing.publish_videos(payload)
        self.assertEqual(
            publisher.call_args.args[-3:],
            ("", "description", "cover.png"),
        )

    def test_web_description_is_forwarded(self):
        publisher = Mock()
        platform = {
            "name": "X",
            "publisher": publisher,
            "login": True,
            "supportsSchedule": False,
        }
        payload = {
            "type": 7,
            "fileList": ["video.mp4"],
            "accountList": ["account.json"],
            "content": "body",
        }
        with patch.dict(publishing.PLATFORMS, {7: platform}):
            publishing.publish_videos(payload)
        self.assertEqual(publisher.call_args.args[-2:], ("", "body"))


if __name__ == "__main__":
    unittest.main()
