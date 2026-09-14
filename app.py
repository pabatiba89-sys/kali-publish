import asyncio
import sqlite3
import sys
import threading
import time
import uuid
from pathlib import Path
from queue import Queue

from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

import conf
from db import connect, initialize
from myUtils.auth import check_cookie
from myUtils.login import (
    douyin_cookie_gen,
    get_ks_cookie,
    get_tencent_cookie,
    xiaohongshu_cookie_gen,
)
from publishing import PLATFORMS, publish_videos
from utils.browser_runtime import chromium_launch_options


LOGIN_HANDLERS = {
    1: xiaohongshu_cookie_gen,
    2: get_tencent_cookie,
    3: douyin_cookie_gen,
    4: get_ks_cookie,
}


def api_response(data=None, message=None, status=200):
    return jsonify({"code": status, "msg": message, "data": data}), status


def create_app(test_config=None):
    app = Flask(__name__)
    CORS(app)
    app.config.update(
        DATABASE_PATH=conf.DATABASE_PATH,
        VIDEO_FOLDER=conf.VIDEO_FOLDER,
        COOKIES_FOLDER=conf.COOKIES_FOLDER,
        MAX_CONTENT_LENGTH=conf.MAX_CONTENT_LENGTH,
    )
    if test_config:
        app.config.update(test_config)

    database_path = Path(app.config["DATABASE_PATH"])
    video_folder = Path(app.config["VIDEO_FOLDER"])
    cookies_folder = Path(app.config["COOKIES_FOLDER"])
    video_folder.mkdir(parents=True, exist_ok=True)
    cookies_folder.mkdir(parents=True, exist_ok=True)
    (conf.BASE_DIR / "logs").mkdir(parents=True, exist_ok=True)
    initialize(database_path)

    @app.get("/health")
    def health():
        return api_response({"status": "ok", "platforms": len(PLATFORMS)})

    @app.get("/api/platforms")
    def platforms():
        data = [
            {"type": key, "name": value["name"], "supportsLogin": value["login"]}
            for key, value in PLATFORMS.items()
        ]
        return api_response(data)

    @app.post("/upload")
    def upload_file():
        uploaded = request.files.get("file")
        if uploaded is None or not uploaded.filename:
            return api_response(None, "file is required", 400)
        filename = secure_filename(uploaded.filename)
        if not filename:
            return api_response(None, "invalid filename", 400)
        stored_name = f"{uuid.uuid4()}_{filename}"
        destination = video_folder / stored_name
        uploaded.save(destination)
        size_mb = round(destination.stat().st_size / (1024 * 1024), 2)
        with connect(database_path) as connection:
            cursor = connection.execute(
                "INSERT INTO file_records (filename, filesize, file_path) VALUES (?, ?, ?)",
                (filename, size_mb, stored_name),
            )
            record_id = cursor.lastrowid
        return api_response(
            {"id": record_id, "filename": filename, "filepath": stored_name, "filesize": size_mb}
        )

    @app.get("/getFiles")
    def get_files():
        with connect(database_path) as connection:
            rows = connection.execute("SELECT * FROM file_records ORDER BY id DESC").fetchall()
        return api_response([dict(row) for row in rows])

    @app.get("/getFile")
    def get_file():
        filename = request.args.get("filename", "")
        if not filename or Path(filename).name != filename:
            return api_response(None, "invalid filename", 400)
        return send_from_directory(video_folder, filename)

    @app.route("/deleteFile", methods=["GET", "DELETE"])
    def delete_file():
        file_id = request.args.get("id", "")
        if not file_id.isdigit():
            return api_response(None, "invalid file id", 400)
        with connect(database_path) as connection:
            row = connection.execute(
                "SELECT * FROM file_records WHERE id = ?", (int(file_id),)
            ).fetchone()
            if row is None:
                return api_response(None, "file not found", 404)
            connection.execute("DELETE FROM file_records WHERE id = ?", (int(file_id),))
        file_path = video_folder / row["file_path"]
        if file_path.is_file():
            file_path.unlink()
        return api_response({"id": int(file_id), "filename": row["filename"]})

    @app.get("/getAccounts")
    def get_accounts():
        name = request.args.get("name", "").strip()
        query = "SELECT * FROM user_info"
        params = ()
        if name:
            query += " WHERE userName = ?"
            params = (name,)
        query += " ORDER BY id DESC"
        with connect(database_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return api_response([list(row) for row in rows])

    @app.get("/getValidAccounts")
    def get_valid_accounts():
        name = request.args.get("name", "").strip()
        query = "SELECT * FROM user_info"
        params = ()
        if name:
            query += " WHERE userName = ?"
            params = (name,)
        with connect(database_path) as connection:
            rows = connection.execute(query, params).fetchall()
            result = [list(row) for row in rows]
            for row in result:
                platform_type = int(row[1])
                if platform_type not in LOGIN_HANDLERS:
                    continue
                try:
                    valid = asyncio.run(check_cookie(platform_type, row[2]))
                except Exception:
                    valid = False
                if not valid:
                    row[4] = 0
                    connection.execute("UPDATE user_info SET status = 0 WHERE id = ?", (row[0],))
        return api_response(result)

    @app.route("/deleteAccount", methods=["GET", "DELETE"])
    def delete_account():
        account_id = request.args.get("id", "")
        if not account_id.isdigit():
            return api_response(None, "invalid account id", 400)
        with connect(database_path) as connection:
            row = connection.execute(
                "SELECT * FROM user_info WHERE id = ?", (int(account_id),)
            ).fetchone()
            if row is None:
                return api_response(None, "account not found", 404)
            connection.execute("DELETE FROM user_info WHERE id = ?", (int(account_id),))
        cookie_path = cookies_folder / row["filePath"]
        if cookie_path.is_file():
            cookie_path.unlink()
        return api_response(None, "account deleted")

    @app.post("/updateUserinfo")
    def update_user_info():
        payload = request.get_json(silent=True) or {}
        try:
            account_id = int(payload["id"])
            platform_type = int(payload["type"])
        except (KeyError, TypeError, ValueError):
            return api_response(None, "id and type must be integers", 400)
        username = str(payload.get("userName", "")).strip()
        if platform_type not in PLATFORMS or not username:
            return api_response(None, "invalid platform type or userName", 400)
        with connect(database_path) as connection:
            cursor = connection.execute(
                "UPDATE user_info SET type = ?, userName = ? WHERE id = ?",
                (platform_type, username, account_id),
            )
        if cursor.rowcount == 0:
            return api_response(None, "account not found", 404)
        return api_response(None, "account updated")

    @app.get("/login")
    def login():
        try:
            platform_type = int(request.args.get("type", ""))
        except ValueError:
            return api_response(None, "invalid platform type", 400)
        account_name = request.args.get("id", "").strip()
        handler = LOGIN_HANDLERS.get(platform_type)
        if handler is None or not account_name:
            return api_response(None, "platform login is unsupported or account name is empty", 400)

        status_queue = Queue()

        def run_login():
            try:
                asyncio.run(handler(account_name, status_queue))
            except Exception as exc:
                app.logger.exception("Login failed")
                status_queue.put(f"error:{type(exc).__name__}")

        threading.Thread(target=run_login, daemon=True).start()

        def stream():
            while True:
                if status_queue.empty():
                    time.sleep(0.1)
                    continue
                message = str(status_queue.get())
                yield f"data: {message}\n\n"
                if message in {"200", "500"} or message.startswith("error:"):
                    break

        response = Response(stream(), mimetype="text/event-stream")
        response.headers["Cache-Control"] = "no-cache"
        response.headers["X-Accel-Buffering"] = "no"
        return response

    @app.post("/postVideo")
    @app.post("/api/publish")
    def post_video():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return api_response(None, "JSON object required", 400)
        try:
            publish_videos(payload)
        except (KeyError, TypeError, ValueError) as exc:
            return api_response(None, str(exc), 400)
        except Exception:
            app.logger.exception("Publish failed")
            return api_response(None, "publish failed", 500)
        return api_response(None)

    @app.post("/postVideoBatch")
    @app.post("/api/publish/batch")
    def post_video_batch():
        payloads = request.get_json(silent=True)
        if not isinstance(payloads, list):
            return api_response(None, "JSON array required", 400)
        try:
            for payload in payloads:
                if not isinstance(payload, dict):
                    raise ValueError("every batch item must be an object")
                publish_videos(payload)
        except (KeyError, TypeError, ValueError) as exc:
            return api_response(None, str(exc), 400)
        except Exception:
            app.logger.exception("Batch publish failed")
            return api_response(None, "batch publish failed", 500)
        return api_response({"count": len(payloads)})

    @app.errorhandler(413)
    def too_large(_error):
        return api_response(None, "file too large", 413)

    return app


app = create_app()


async def browser_self_test():
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**chromium_launch_options(headless=True))
        try:
            page = await browser.new_page()
            await page.set_content("<title>kali-publish-ok</title>")
            if await page.title() != "kali-publish-ok":
                raise RuntimeError("Chrome page test failed")
        finally:
            await browser.close()
    print("browser-self-test-ok")


def main():
    if "--self-test-browser" in sys.argv:
        asyncio.run(browser_self_test())
        return
    app.run(host=conf.HOST, port=conf.PORT, debug=conf.DEBUG_MODE)


if __name__ == "__main__":
    main()
