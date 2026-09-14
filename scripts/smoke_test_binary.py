import argparse
import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path)
    args = parser.parse_args()
    binary = args.binary.resolve()
    if not binary.is_file():
        raise SystemExit(f"Binary does not exist: {binary}")

    port = free_port()
    with tempfile.TemporaryDirectory() as data_directory:
        environment = os.environ.copy()
        environment.update(
            HOST="127.0.0.1",
            PORT=str(port),
            KALI_PUBLISH_DATA_DIR=data_directory,
            LOCAL_CHROME_HEADLESS="true",
        )
        browser_test = subprocess.run(
            [str(binary), "--self-test-browser"],
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if browser_test.returncode != 0 or "browser-self-test-ok" not in browser_test.stdout:
            output = (browser_test.stdout + browser_test.stderr)[-4000:]
            raise SystemExit(f"Packaged browser self-test failed:\n{output}")

        process = subprocess.Popen(
            [str(binary)],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    output = process.stdout.read() if process.stdout else ""
                    raise SystemExit(f"Binary exited with {process.returncode}:\n{output[-4000:]}")
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                        payload = json.load(response)
                    if response.status == 200 and payload.get("data", {}).get("status") == "ok":
                        print("binary-smoke-test-ok")
                        return
                except Exception:
                    time.sleep(1)
            raise SystemExit("Timed out waiting for the packaged backend")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


if __name__ == "__main__":
    main()
