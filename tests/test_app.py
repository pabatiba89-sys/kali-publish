import io
import json
import stat
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
        self.assertEqual([item["type"] for item in platforms], [1, 2, 3, 4, 5, 6, 7, 8, 9])
        x_platform = next(item for item in platforms if item["type"] == 7)
        self.assertEqual(x_platform["accountMode"], "api")
        self.assertTrue(x_platform["supportsCredentialImport"])
        self.assertFalse(x_platform["supportsSchedule"])

    def test_import_api_account_stores_secret_only_in_restricted_file(self):
        token = "secret-token-that-must-not-be-returned"
        response = self.client.post(
            "/api/accounts/import",
            json={
                "type": 7,
                "userName": "brand-x",
                "credentials": {"access_token": token},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(token, response.get_data(as_text=True))
        account_id = response.get_json()["data"]["id"]

        with closing(sqlite3.connect(self.application.config["DATABASE_PATH"])) as connection:
            row = connection.execute(
                "SELECT filePath, status FROM user_info WHERE id = ?", (account_id,)
            ).fetchone()
        credential_path = Path(self.application.config["COOKIES_FOLDER"]) / row[0]
        stored = json.loads(credential_path.read_text(encoding="utf-8"))
        self.assertEqual(stored, {"platform": "x", "access_token": token})
        self.assertEqual(stat.S_IMODE(credential_path.stat().st_mode), 0o600)
        self.assertEqual(row[1], 1)

        valid_accounts = self.client.get("/getValidAccounts?name=brand-x").get_json()["data"]
        self.assertEqual(valid_accounts[0][4], 1)

    def test_import_api_account_validates_required_fields(self):
        response = self.client.post(
            "/api/accounts/import",
            json={"type": 8, "userName": "brand-instagram", "credentials": {}},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("access_token", response.get_json()["msg"])
        self.assertIn("ig_user_id", response.get_json()["msg"])

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
