import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from uploader.youtube_uploader import main as youtube


class YouTubeLoginTests(unittest.TestCase):
    def test_detects_completed_login_from_chrome_history(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = Path(temporary_directory)
            default = profile / "Default"
            default.mkdir()
            with closing(sqlite3.connect(default / "History")) as connection:
                connection.execute(
                    "CREATE TABLE urls (url TEXT NOT NULL, last_visit_time INTEGER NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO urls (url, last_visit_time) VALUES (?, ?)",
                    ("https://studio.youtube.com/channel/UC-test", 1),
                )
                connection.commit()

            self.assertEqual(
                youtube._studio_channel_from_history(profile),
                "https://studio.youtube.com/channel/UC-test",
            )

    def test_ignores_google_sign_in_history(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = Path(temporary_directory)
            default = profile / "Default"
            default.mkdir()
            with closing(sqlite3.connect(default / "History")) as connection:
                connection.execute(
                    "CREATE TABLE urls (url TEXT NOT NULL, last_visit_time INTEGER NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO urls (url, last_visit_time) VALUES (?, ?)",
                    ("https://accounts.google.com/signin", 1),
                )
                connection.commit()

            self.assertEqual(youtube._studio_channel_from_history(profile), "")


if __name__ == "__main__":
    unittest.main()
