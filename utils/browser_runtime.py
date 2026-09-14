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
