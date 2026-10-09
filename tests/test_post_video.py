import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch

from myUtils import postVideo
from uploader.tk_uploader.main import TiktokVideo


class BrowserPublisherWiringTests(unittest.TestCase):
    @patch.object(postVideo.asyncio, 'run')
    @patch.object(postVideo, 'AlipayVideo')
    def test_alipay_passes_schedule_to_uploader(self, video_class, run):
        scheduled = (datetime.now(timezone.utc) + timedelta(days=1)).replace(second=0, microsecond=0)
        postVideo.post_video_alipay('title', ['video.mp4'], [], ['account.json'],
                                   enableTimer=True, endpublishTime=scheduled.isoformat())
        self.assertEqual(video_class.call_args.kwargs['publish_date'].timestamp(), scheduled.timestamp())
        run.assert_called_once()

    @patch.object(postVideo.asyncio, 'run')
    def test_alipay_schedule_without_time_does_not_publish(self, run):
        with self.assertRaisesRegex(ValueError, '时间'):
            postVideo.post_video_alipay('title', ['video.mp4'], [], ['account.json'], enableTimer=True)
        run.assert_not_called()

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
        self.assertEqual(video_class.call_args.kwargs["description"], "")
        self.assertIsNone(video_class.call_args.kwargs["thumbnail_path"])
        run.assert_called_once()

    def test_tiktok_caption_includes_description(self):
        video = TiktokVideo(
            "Title",
            "video.mp4",
            ["tag"],
            0,
            "account.json",
            description="Description",
        )
        self.assertEqual(getattr(video, "caption", None), "Title\nDescription")

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
        self.assertEqual(video_class.call_args.kwargs["visibility"], "public")
        self.assertEqual(video_class.call_args.kwargs["description"], "")
        run.assert_called_once()

    @patch.object(postVideo.asyncio, "run")
    @patch.object(postVideo, "AlipayVideo")
    def test_alipay_constructor_receives_metadata(self, video_class, run):
        instance = Mock()
        instance.main.return_value = "alipay-main"
        video_class.return_value = instance
        postVideo.post_video_alipay(
            "title",
            ["video.mp4"],
            ["tag"],
            ["account.json"],
            description="description",
            thumbnail_path="cover.png",
            collection_name="series",
        )
        self.assertEqual(video_class.call_args.kwargs["desc"], "description")
        self.assertEqual(video_class.call_args.kwargs["thumbnail_path"].name, "cover.png")
        self.assertEqual(video_class.call_args.kwargs["collection_name"], "series")
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
