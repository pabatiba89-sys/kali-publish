"""Recovery limited to navigation reads and browsers owned by a publish task."""
import asyncio
import time

from playwright.async_api import Error as PlaywrightError


async def navigation_read(operation, timeout=15):
    """Retry a read invalidated by navigation; never retry a publishing click."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return await operation()
        except PlaywrightError as exc:
            if ('Execution context was destroyed' not in str(exc)
                    and 'Cannot find context with specified id' not in str(exc)):
                raise
            if time.monotonic() >= deadline:
                raise
            await asyncio.sleep(0.1)


async def close_owned_browser(context, browser, logger, timeout=10):
    """Close only this launched browser, including a bounded CDP fallback."""
    session = None
    if browser is not None and hasattr(browser, 'new_browser_cdp_session'):
        try:
            session = await asyncio.wait_for(browser.new_browser_cdp_session(), min(3, timeout))
        except Exception:
            pass
    if context is not None:
        # Closing pages first avoids a lingering unload dialog holding up context.close.
        async def close_page(page):
            try:
                await asyncio.wait_for(page.close(run_before_unload=False), timeout)
            except Exception:
                logger.warning('发布页面关闭未完成，继续清理本次浏览器')
        await asyncio.gather(*(close_page(page) for page in getattr(context, 'pages', [])))
        try:
            await asyncio.wait_for(context.close(), timeout)
        except Exception:
            logger.warning('发布会话关闭未完成，继续清理本次浏览器')
    if browser is None:
        return
    try:
        await asyncio.wait_for(browser.close(), timeout)
        logger.info('本次发布浏览器已关闭')
        return
    except Exception:
        logger.warning('常规关窗未完成，尝试关闭本次浏览器连接')
    if session is not None:
        try:
            await asyncio.wait_for(session.send('Browser.close'), timeout)
        except Exception:
            # Browser.close can disconnect the channel before replying.
            pass
        if hasattr(browser, 'is_connected') and not browser.is_connected():
            logger.info('本次发布浏览器已通过兜底关闭')
            return
    logger.warning('本次发布浏览器关闭未确认；保留原发布结果，请勿因此重复发布')
