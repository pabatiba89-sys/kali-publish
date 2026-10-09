import io
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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
            [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
        )
        for platform_type in (7, 8, 9, 10):
            platform = next(item for item in platforms if item["type"] == platform_type)
            self.assertEqual(platform["accountMode"], "browser")
            self.assertTrue(platform["supportsLogin"])
            self.assertFalse(platform["supportsCredentialImport"])
            self.assertEqual(platform["supportsSchedule"], platform_type == 10)
        personal = next(item for item in platforms if item['type'] == 11)
        self.assertTrue(personal['experimental'])
        self.assertTrue(personal['defaultDryRun'])
        self.assertTrue(personal['supportsSchedule'])
        self.assertIn('含AI生成内容', personal['contentDeclarations'])
        self.assertIn(11, app_module.LOGIN_HANDLERS)

    def test_pdd_dry_run_result_is_not_reported_as_published(self):
        result = {'type': 11, 'dryRun': True, 'results': [{'status': 'prepared', 'published': False}]}
        with patch.object(app_module, 'publish_videos', return_value=result):
            response = self.client.post('/api/publish', json={'type': 11})
            batch = self.client.post('/api/publish/batch', json=[{'type': 11}])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['data'], result)
        self.assertEqual(batch.get_json()['data']['results'], [result])

    def test_pdd_missing_declaration_fails_before_upload(self):
        response = self.client.post('/api/publish', json={
            'type': 11, 'fileList': ['unused.mp4'], 'accountList': ['unused.json']})
        self.assertEqual(response.status_code, 400)
        self.assertIn('contentDeclaration', response.get_json()['msg'])

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

    def test_upload_from_url_accepts_cross_origin_preflight(self):
        response = self.client.options(
            "/uploadFromUrl",
            headers={
                "Origin": "http://127.0.0.1:4321",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("Access-Control-Allow-Origin"),
            "http://127.0.0.1:4321",
        )

    def test_upload_from_url_downloads_and_records_video(self):
        def fake_download(_url, destination, _max_bytes):
            destination.write_bytes(b"remote-video")

        with patch.object(
            app_module, "_download_remote_file", side_effect=fake_download, create=True
        ):
            response = self.client.post(
                "/uploadFromUrl",
                json={"videoUrl": "https://cdn.example.com/path/video.mp4"},
                headers={"Origin": "http://127.0.0.1:4321"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("Access-Control-Allow-Origin"),
            "http://127.0.0.1:4321",
        )
        record = response.get_json()["data"]
        self.assertEqual(record["filename"], "video.mp4")
        self.assertTrue((Path(self.application.config["VIDEO_FOLDER"]) / record["filepath"]).is_file())
        files = self.client.get("/getFiles").get_json()["data"]
        self.assertEqual(files[0]["file_path"], record["filepath"])

    def test_remote_download_ignores_https_certificate_errors(self):
        response = MagicMock()
        response.headers = {}
        response.read.return_value = b""
        response.__enter__.return_value = response
        opener = MagicMock()
        opener.open.return_value = response

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(app_module, "_validate_remote_url"),
            patch.object(app_module, "build_opener", return_value=opener) as builder,
        ):
            app_module._download_remote_file(
                "https://cdn.example.com/video.mp4",
                Path(directory) / "video.mp4",
                1024,
            )

        https_handlers = [
            handler
            for handler in builder.call_args.args
            if type(handler).__name__ == "HTTPSHandler"
        ]
        self.assertEqual(len(https_handlers), 1)
        self.assertFalse(https_handlers[0]._context.check_hostname)
        self.assertEqual(https_handlers[0]._context.verify_mode, app_module.ssl.CERT_NONE)

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

    def test_valid_accounts_only_checks_tencent_cookie(self):
        with closing(sqlite3.connect(self.application.config["DATABASE_PATH"])) as connection:
            connection.executemany(
                "INSERT INTO user_info (type, filePath, userName, status) VALUES (?, ?, ?, ?)",
                [
                    (2, "tencent.json", "video-channel", 1),
                    (7, "x-profile", "x-account", 1),
                ],
            )
            connection.commit()

        cookie_check = AsyncMock(return_value=False)
        with patch.object(app_module, "check_cookie", cookie_check):
            accounts = self.client.get("/getValidAccounts").get_json()["data"]

        cookie_check.assert_awaited_once_with(2, "tencent.json")
        statuses = {int(account[1]): int(account[4]) for account in accounts}
        self.assertEqual(statuses[2], 0)
        self.assertEqual(statuses[7], 1)

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

    def test_delete_tiktok_account_removes_dedicated_profile(self):
        profile_name = "tiktok-test-profile"
        profile_path = Path(self.application.config["COOKIES_FOLDER"]) / profile_name
        profile_path.mkdir()
        (profile_path / "Local State").write_text("{}", encoding="utf-8")
        with closing(sqlite3.connect(self.application.config["DATABASE_PATH"])) as connection:
            cursor = connection.execute(
                "INSERT INTO user_info (type, filePath, userName, status) VALUES (?, ?, ?, ?)",
                (5, profile_name, "tiktok-test", 1),
            )
            account_id = cursor.lastrowid
            connection.commit()

        response = self.client.delete(f"/deleteAccount?id={account_id}")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(profile_path.exists())

    def test_delete_web_account_removes_dedicated_profile(self):
        profile_name = "web-7-test-profile"
        profile_path = Path(self.application.config["COOKIES_FOLDER"]) / profile_name
        profile_path.mkdir()
        (profile_path / "Local State").write_text("{}", encoding="utf-8")
        with closing(sqlite3.connect(self.application.config["DATABASE_PATH"])) as connection:
            cursor = connection.execute(
                "INSERT INTO user_info (type, filePath, userName, status) VALUES (?, ?, ?, ?)",
                (7, profile_name, "x-test", 1),
            )
            account_id = cursor.lastrowid
            connection.commit()

        response = self.client.delete(f"/deleteAccount?id={account_id}")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(profile_path.exists())

    def test_publish_validation_and_dispatch(self):
        self.assertEqual(self.client.post("/api/publish", json={}).status_code, 400)
        payload = {"type": 1, "fileList": ["a.mp4"], "accountList": ["a.json"]}
        with patch.object(app_module, "publish_videos", return_value=None) as publisher:
            self.assertEqual(self.client.post("/api/publish", json=payload).status_code, 200)
            publisher.assert_called_once_with(payload)


if __name__ == "__main__":
    unittest.main()
