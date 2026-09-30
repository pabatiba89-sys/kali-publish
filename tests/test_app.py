import io
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import app as app_module


class BackendApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        root = Path(self.temp_directory.name)
        self.application = app_module.create_app(
            {
                "TESTING": True,
                "DATABASE_PATH": root / "test.db",
                "VIDEO_FOLDER": root / "videos",
                "COOKIES_FOLDER": root / "cookies",
            }
        )
        self.client = self.application.test_client()

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_health_and_platforms(self):
        self.assertEqual(self.client.get("/health").get_json()["data"]["status"], "ok")
        platforms = self.client.get("/api/platforms").get_json()["data"]
        self.assertEqual(
            [item["type"] for item in platforms],
            [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        )
        for platform_type in (7, 8, 9, 10):
            platform = next(item for item in platforms if item["type"] == platform_type)
            self.assertEqual(platform["accountMode"], "browser")
            self.assertTrue(platform["supportsLogin"])
            self.assertFalse(platform["supportsCredentialImport"])
            self.assertFalse(platform["supportsSchedule"])

    def test_official_api_import_endpoint_is_removed(self):
        response = self.client.post("/api/accounts/import", json={"type": 7})
        self.assertEqual(response.status_code, 404)

    def test_upload_list_download_and_delete(self):
        response = self.client.post(
            "/upload",
            data={"file": (io.BytesIO(b"video"), "sample.mp4")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        record = response.get_json()["data"]
        files = self.client.get("/getFiles").get_json()["data"]
        self.assertEqual(files[0]["filename"], "sample.mp4")
        download = self.client.get(f"/getFile?filename={record['filepath']}")
        self.assertEqual(download.data, b"video")
        download.close()
        self.assertEqual(self.client.delete(f"/deleteFile?id={record['id']}").status_code, 200)
        self.assertEqual(self.client.get("/getFiles").get_json()["data"], [])

    def test_account_filter_is_parameterized(self):
        with closing(sqlite3.connect(self.application.config["DATABASE_PATH"])) as connection:
            connection.execute(
                "INSERT INTO user_info (type, filePath, userName, status) VALUES (?, ?, ?, ?)",
                (1, "cookie.json", "alice", 1),
            )
            connection.commit()
        self.assertEqual(len(self.client.get("/getAccounts?name=alice").get_json()["data"]), 1)
        injected = self.client.get("/getAccounts?name=' OR 1=1 --").get_json()["data"]
        self.assertEqual(injected, [])

    def test_delete_youtube_account_removes_dedicated_profile(self):
        profile_name = "youtube-test-profile"
        profile_path = Path(self.application.config["COOKIES_FOLDER"]) / profile_name
        profile_path.mkdir()
        (profile_path / "Local State").write_text("{}", encoding="utf-8")
        with closing(sqlite3.connect(self.application.config["DATABASE_PATH"])) as connection:
            cursor = connection.execute(
                "INSERT INTO user_info (type, filePath, userName, status) VALUES (?, ?, ?, ?)",
                (6, profile_name, "youtube-test", 1),
            )
            account_id = cursor.lastrowid
            connection.commit()

        response = self.client.delete(f"/deleteAccount?id={account_id}")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(profile_path.exists())

    def test_publish_validation_and_dispatch(self):
        self.assertEqual(self.client.post("/api/publish", json={}).status_code, 400)
        payload = {"type": 1, "fileList": ["a.mp4"], "accountList": ["a.json"]}
        with patch.object(app_module, "publish_videos") as publisher:
            self.assertEqual(self.client.post("/api/publish", json=payload).status_code, 200)
            publisher.assert_called_once_with(payload)


if __name__ == "__main__":
    unittest.main()
