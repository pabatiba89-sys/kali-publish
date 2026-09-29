import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from myUtils import postVideo


class BrowserPublisherWiringTests(unittest.TestCase):
    def test_publish_date_preserves_an_explicit_instant(self):
        parsed = postVideo.parse_publish_date("2026-10-01T02:00:00+00:00")
        self.assertEqual(parsed.timestamp(), datetime(2026, 10, 1, 2, tzinfo=timezone.utc).timestamp())

    @patch.object(postVideo.asyncio, "run")
    @patch.object(postVideo, "TiktokVideo")
    def test_tiktok_constructor_receives_supported_arguments(self, video_class, run):
        instance = Mock()
        instance.main.return_value = "tiktok-main"
        video_class.return_value = instance
        postVideo.post_video_tk(
            "title", ["video.mp4"], ["tag"], ["account.json"], enableTimer=False
        )
        self.assertEqual(len(video_class.call_args.args), 5)
        self.assertEqual(video_class.call_args.args[3], 0)
        run.assert_called_once()

    @patch.object(postVideo.asyncio, "run")
    @patch.object(postVideo, "YouTubeVideo")
    def test_youtube_constructor_receives_supported_arguments(self, video_class, run):
        instance = Mock()
        instance.main.return_value = "youtube-main"
        video_class.return_value = instance
        postVideo.post_video_youtube(
            "title", ["video.mp4"], ["tag"], ["account.json"], enableTimer=False
        )
        self.assertEqual(len(video_class.call_args.args), 4)
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
