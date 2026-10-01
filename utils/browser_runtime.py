import asyncio
import os
import platform
import shutil
import socket
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from conf import LOCAL_CHROME_PATH

STORAGE_STATE_FILENAME = "storage-state.json"


def chromium_launch_options(headless: bool, args=None) -> dict:
    """Return Playwright options for the user's installed Google Chrome."""
    options = {"headless": headless}
    if args:
        options["args"] = list(args)

    if LOCAL_CHROME_PATH:
        options["executable_path"] = LOCAL_CHROME_PATH
    else:
        options["channel"] = "chrome"

    return options


def chrome_storage_state_path(account_file) -> Path:
    account_path = Path(account_file)
    if account_path.is_dir():
        return account_path / STORAGE_STATE_FILENAME
    return account_path


def reserve_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


async def save_chrome_storage_state(debug_port: int, destination: Path) -> bool:
    """Export a regular Chrome session through local CDP without exposing it."""
    from playwright.async_api import async_playwright

    endpoint = f"http://127.0.0.1:{int(debug_port)}"
    deadline = time.monotonic() + 15
    async with async_playwright() as playwright:
        browser = None
        while browser is None:
            try:
                browser = await playwright.chromium.connect_over_cdp(
                    endpoint, timeout=1000
                )
            except Exception:
                if time.monotonic() >= deadline:
                    return False
                await asyncio.sleep(0.1)
        try:
            if not browser.contexts:
                return False
            destination = Path(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            await browser.contexts[0].storage_state(path=destination)
            return destination.is_file()
        finally:
            await browser.close()


def chrome_profile_has_cookies(
    profile_dir: Path, domains: tuple[str, ...], required_names: set[str]
) -> bool:
    """Check Chrome cookie names without reading or decrypting their values."""
    required = {str(name) for name in required_names if str(name)}
    normalized_domains = tuple(
        str(domain).lower().lstrip(".") for domain in domains if str(domain).strip()
    )
    if not required or not normalized_domains:
        return False
    cookie_paths = (
        profile_dir / "Default" / "Cookies",
        profile_dir / "Default" / "Network" / "Cookies",
        profile_dir / "Cookies",
        profile_dir / "Network" / "Cookies",
    )
    host_conditions = " OR ".join(
        "(LOWER(host_key) = ? OR LOWER(host_key) LIKE ?)" for _ in normalized_domains
    )
    name_placeholders = ", ".join("?" for _ in required)
    host_params = [
        value
        for domain in normalized_domains
        for value in (domain, f"%.{domain}")
    ]
    for cookie_path in cookie_paths:
        if not cookie_path.is_file():
            continue
        try:
            uri = f"{cookie_path.resolve().as_uri()}?mode=ro"
            with closing(sqlite3.connect(uri, uri=True, timeout=0.2)) as connection:
                rows = connection.execute(
                    f"SELECT DISTINCT name FROM cookies WHERE ({host_conditions}) "
                    f"AND name IN ({name_placeholders})",
                    (*host_params, *sorted(required)),
                ).fetchall()
            present = {str(row[0]) for row in rows}
            if required.issubset(present):
                return True
        except (OSError, sqlite3.Error):
            continue
    return False


def resolve_chrome_executable() -> Path:
    """Resolve the regular Chrome executable used for non-automated sign-in."""
    if LOCAL_CHROME_PATH:
        configured = Path(LOCAL_CHROME_PATH).expanduser()
        if configured.is_file():
            return configured.resolve()
        raise FileNotFoundError(f"LOCAL_CHROME_PATH does not exist: {configured}")

    system = platform.system()
    candidates = []
    if system == "Darwin":
        candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
    elif system == "Windows":
        for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            root = os.getenv(variable)
            if root:
                candidates.append(Path(root) / "Google/Chrome/Application/chrome.exe")
    else:
        for command in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
            resolved = shutil.which(command)
            if resolved:
                candidates.append(Path(resolved))

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "Google Chrome was not found; install Chrome or set LOCAL_CHROME_PATH"
    )
