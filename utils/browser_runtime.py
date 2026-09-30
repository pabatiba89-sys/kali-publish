import os
import platform
import shutil
from pathlib import Path

from conf import LOCAL_CHROME_PATH


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
