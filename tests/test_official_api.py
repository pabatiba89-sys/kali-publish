import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

from uploader.official_api import (
    FacebookReelPublisher,
    InstagramReelPublisher,
    PlatformApiError,
    XVideoPublisher,
    build_caption,
    load_credentials,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class OfficialApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.video = Path(self.temp_directory.name) / "video.mp4"
        self.video.write_bytes(b"video-data")

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_load_credentials_and_caption(self):
        credential_file = Path(self.temp_directory.name) / "x.json"
        credential_file.write_text(
            json.dumps({"platform": "x", "access_token": "token"}), encoding="utf-8"
        )
        self.assertEqual(load_credentials(credential_file, 7)["access_token"], "token")
        self.assertEqual(build_caption("Title", ["one", "#two"]), "Title #one #two")

    def test_x_chunked_upload_and_post(self):
        session = Mock()
        session.request.side_effect = [
            FakeResponse({"data": {"id": "media-1"}}),
            FakeResponse({"data": {}}),
            FakeResponse({"data": {"processing_info": {"state": "pending", "check_after_secs": 1}}}),
            FakeResponse({"data": {"processing_info": {"state": "succeeded"}}}),
            FakeResponse({"data": {"id": "post-1", "text": "Title #tag"}}, status_code=201),
        ]
        publisher = XVideoPublisher(
            {"access_token": "token"}, session=session, sleep=lambda _seconds: None
        )
        result = publisher.publish(self.video, "Title #tag")
        self.assertEqual(result["data"]["id"], "post-1")
        urls = [call.args[1] for call in session.request.call_args_list]
        self.assertEqual(
            urls,
            [
                "https://api.x.com/2/media/upload/initialize",
                "https://api.x.com/2/media/upload/media-1/append",
                "https://api.x.com/2/media/upload/media-1/finalize",
                "https://api.x.com/2/media/upload",
                "https://api.x.com/2/tweets",
            ],
        )

    def test_instagram_resumable_reel_publish(self):
        session = Mock()
        session.request.side_effect = [
            FakeResponse({"id": "container-1", "uri": "https://rupload.facebook.com/container-1"}),
            FakeResponse({"success": True}),
            FakeResponse({"status_code": "FINISHED"}),
            FakeResponse({"id": "reel-1"}),
        ]
        publisher = InstagramReelPublisher(
            {"access_token": "token", "ig_user_id": "ig-1"},
            session=session,
            sleep=lambda _seconds: None,
        )
        result = publisher.publish(self.video, "Caption")
        self.assertEqual(result["id"], "reel-1")
        self.assertEqual(
            session.request.call_args_list[1].args[1], "https://rupload.facebook.com/container-1"
        )

    def test_facebook_reel_publish_and_schedule(self):
        session = Mock()
        session.request.side_effect = [
            FakeResponse({"video_id": "video-1", "upload_url": "https://rupload.facebook.com/video-1"}),
            FakeResponse({"success": True}),
            FakeResponse({"success": True}),
        ]
        publisher = FacebookReelPublisher(
            {"access_token": "token", "page_id": "page-1"}, session=session
        )
        publish_date = datetime(2026, 10, 1, 10, 0, 0)
        result = publisher.publish(self.video, "Caption", publish_date=publish_date)
        self.assertTrue(result["success"])
        finish_data = session.request.call_args_list[2].kwargs["data"]
        self.assertEqual(finish_data["video_state"], "SCHEDULED")
        self.assertEqual(finish_data["scheduled_publish_time"], str(int(publish_date.timestamp())))

    def test_meta_upload_url_is_restricted_to_meta_host(self):
        session = Mock()
        session.request.return_value = FakeResponse(
            {"id": "container-1", "uri": "https://attacker.example/steal"}
        )
        publisher = InstagramReelPublisher(
            {"access_token": "token", "ig_user_id": "ig-1"}, session=session
        )
        with self.assertRaises(PlatformApiError):
            publisher.publish(self.video, "Caption")


if __name__ == "__main__":
    unittest.main()
