from __future__ import annotations

import asyncio
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

from utils.browser_runtime import chromium_launch_options
from utils.log import pdd_logger


PDD_PUBLISH_URL = "https://live.pinduoduo.com/n-creator/video/home"
BEIJING = timezone(timedelta(hours=8))
PROCESSING_TIMEOUT = 15 * 60
CONTENT_DECLARATIONS = (
    "内容无需标注", "含AI生成内容", "含虚构演绎内容",
    "内容含营销信息", "内容为转载", "个人观点，仅供参考",
)
DATE_INPUT = 'input[data-testid="beast-core-datePicker-htmlInput"]'
PICKER = '[data-testid="beast-core-datePicker-dropdown-contentRoot"]:visible'
VIDEO_INPUT = 'input[type="file"][accept*=".mp4"], input[type="file"][accept*="video"]'
STATEMENT = '[class*="ContentDeclaration_statement"]'


def normalize_publish_date(value, *, now=None):
    try:
        target = value if isinstance(value, datetime) else datetime.fromisoformat(
            str(value).strip().replace("Z", "+00:00")
        )
    except (ValueError, TypeError) as exc:
        raise ValueError("拼多多定时发布时间无效，请使用 YYYY-MM-DD HH:mm:ss") from exc
    target = target.replace(tzinfo=BEIJING) if target.tzinfo is None else target.astimezone(BEIJING)
    current = now or datetime.now(BEIJING)
    if current.tzinfo is None:
        current = current.replace(tzinfo=BEIJING)
    if target.microsecond:
        raise ValueError("拼多多定时时间仅支持整秒")
    if target <= current:
        raise ValueError("拼多多定时时间必须晚于当前时间，请预留登录和上传耗时")
    # The personal page's allowed range is not yet verified. Respect disabled
    # controls and validation on the actual page instead of inventing a limit.
    return target


def validate_options(declaration, dry_run):
    if declaration not in CONTENT_DECLARATIONS:
        raise ValueError("拼多多必须明确指定 contentDeclaration：" + "、".join(CONTENT_DECLARATIONS))
    if not isinstance(dry_run, bool):
        raise ValueError("dryRun 必须为 JSON 布尔值 true 或 false")


def has_personal_session(cookies, *, now=None):
    """Conservative first-version session check; never log cookie values."""
    current = time.time() if now is None else now
    return any(
        cookie.get("name") == "PDDAccessToken"
        and cookie.get("domain", "").lstrip(".") in {
            "pinduoduo.com", "live.pinduoduo.com", "yangkeduo.com", "live.yangkeduo.com",
        }
        and bool(cookie.get("value"))
        and (cookie.get("expires", -1) == -1 or cookie.get("expires", 0) > current)
        for cookie in cookies
    )


async def logged_in(page, context):
    if urlsplit(page.url).hostname != "live.pinduoduo.com" or "/n-creator/" not in urlsplit(page.url).path:
        return False
    if not has_personal_session(await context.cookies()):
        return False
    blocked = page.get_by_text(re.compile(r"扫码登录|验证码登录|手机号登录|加载中|服务器出错"))
    if await blocked.locator("visible=true").count():
        return False
    upload = page.get_by_role("button", name="添加视频", exact=True)
    return (await upload.count() == 1 and await upload.is_visible()
            and await upload.is_enabled() and await page.locator(VIDEO_INPUT).count() == 1
            and await page.get_by_text("退出登录", exact=True).locator("visible=true").count() == 1)


async def wait_for_login(page, context, timeout=PROCESSING_TIMEOUT):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if page.is_closed():
            raise RuntimeError("拼多多登录窗口已关闭，未发布视频")
        if await logged_in(page, context):
            return
        await asyncio.sleep(0.5)
    raise TimeoutError("未能确认拼多多个人账号登录完成，未发布视频；请重新登录")


async def save_session(context, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        await asyncio.wait_for(context.storage_state(path=temporary), timeout=10)
        temporary.chmod(0o600)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


async def close_browser(context, browser):
    try:
        if context is not None:
            await asyncio.wait_for(context.close(), timeout=10)
    except Exception:
        pdd_logger.warning("拼多多会话关闭未完成，继续关闭本次浏览器")
    finally:
        try:
            await asyncio.wait_for(browser.close(), timeout=10)
        except Exception:
            # Cleanup cannot turn a confirmed publication into a reported failure.
            pdd_logger.warning("拼多多浏览器未能自动关闭，请手动关闭本次窗口；不要因此重复发布")


async def pdd_cookie_gen(account_file, headless=False, timeout=PROCESSING_TIMEOUT):
    if headless:
        raise ValueError("拼多多个人账号登录需要可见浏览器")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**chromium_launch_options(False))
        context = None
        try:
            context = await browser.new_context(viewport={"width": 1440, "height": 1100})
            page = await context.new_page()
            await page.goto(PDD_PUBLISH_URL, wait_until="domcontentloaded", timeout=120000)
            pdd_logger.info("请在浏览器中完成拼多多个人账号登录；不要进入商家后台")
            await wait_for_login(page, context, timeout)
            await save_session(context, account_file)
            return {"success": True, "status": "logged_in", "message": "个人账号登录成功"}
        except Exception:
            return {"success": False, "status": "login_unconfirmed", "message": "个人账号登录未确认或窗口已关闭"}
        finally:
            await close_browser(context, browser)


async def cookie_auth(account_file):
    if not Path(account_file).is_file():
        return False
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**chromium_launch_options(True))
        context = None
        try:
            context = await browser.new_context(storage_state=account_file)
            page = await context.new_page()
            await page.goto(PDD_PUBLISH_URL, wait_until="domcontentloaded", timeout=120000)
            await wait_for_login(page, context, timeout=15)
            return True
        except Exception:
            return False
        finally:
            await close_browser(context, browser)


class PDDVideo:
    """Personal creator UI adapter. Dry run is the safe default until live verification."""

    def __init__(self, title, file_path, tags, account_file, *, description="",
                 content_declaration=None, publish_date=None, dry_run=True):
        validate_options(content_declaration, dry_run)
        self.file_path = Path(file_path)
        self.account_file = Path(account_file)
        self.content_declaration = content_declaration
        self.publish_date = normalize_publish_date(publish_date) if publish_date is not None else None
        self.dry_run = dry_run
        tag_text = " ".join(f"#{str(tag).lstrip('#')}" for tag in tags or [] if str(tag).lstrip('#'))
        self.caption = "\n".join(str(part).strip() for part in (title, description, tag_text) if str(part or "").strip())

    async def wait_upload(self, page, timeout=PROCESSING_TIMEOUT):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if await page.get_by_text(re.compile(r"上传失败|视频格式不支持|视频过大")).locator("visible=true").count():
                raise RuntimeError("拼多多视频上传失败，已停止发布")
            if await page.get_by_text("视频上传成功", exact=False).locator("visible=true").count():
                return
            await asyncio.sleep(0.25)
        raise TimeoutError("拼多多视频上传或处理超过 15 分钟，未提交发布")

    async def set_declaration(self, page, timeout=30000):
        statement = page.locator(STATEMENT).locator("visible=true")
        await statement.locator('[data-testid="beast-core-select"]').click(timeout=timeout)
        option = page.locator('[class*="ContentDeclaration_title"]:visible').filter(
            has_text=re.compile(r"^" + re.escape(self.content_declaration) + r"(?:\s|（|\(|$)")
        )
        await option.click(timeout=timeout)
        await self.verify_declaration(page)

    async def verify_declaration(self, page):
        statement = page.locator(STATEMENT).locator("visible=true")
        if await statement.count() != 1:
            raise RuntimeError("拼多多内容声明控件未确认，已停止发布")
        if self.content_declaration not in await statement.inner_text():
            raise RuntimeError("拼多多内容声明与请求不一致，已停止发布")
        # Options visible inside the container do not prove a selection.
        if await page.locator('[class*="ContentDeclaration_title"]:visible').count():
            raise RuntimeError("拼多多内容声明尚未确认，已停止发布")

    async def choose_mode(self, page, label, timeout=30000):
        radio = page.get_by_role("radio", name=label, exact=True)
        if await radio.count() == 1:
            await radio.check(timeout=timeout)
        else:
            await page.locator('label[data-testid="beast-core-radio"]').filter(
                has_text=re.compile(r"^\s*" + label + r"\s*$")
            ).click(timeout=timeout)

    async def mode_checked(self, page, label):
        radio = page.get_by_role("radio", name=label, exact=True)
        if await radio.count() != 1:
            radio = page.locator('label[data-testid="beast-core-radio"]').filter(
                has_text=re.compile(r"^\s*" + label + r"\s*$")
            ).locator('input[type="radio"]')
        return await radio.count() == 1 and await radio.is_checked()

    async def set_schedule(self, page, timeout=30000):
        if self.publish_date is None:
            await self.choose_mode(page, "立即发布", timeout)
            return
        target = normalize_publish_date(self.publish_date)
        await self.choose_mode(page, "定时发布", timeout)
        date = page.locator(DATE_INPUT).locator("visible=true")
        await date.click(timeout=timeout)
        picker = page.locator(PICKER)
        await picker.wait_for(state="visible", timeout=timeout)
        if await date.is_editable():
            await date.fill(target.strftime("%Y-%m-%d %H:%M:%S"), timeout=timeout)
        else:
            await self.pick_datetime(page, picker, target, timeout)
        await picker.get_by_role("button", name="确认", exact=True).click(timeout=timeout)
        await picker.wait_for(state="hidden", timeout=timeout)
        await date.blur(timeout=timeout)
        await self.verify_schedule(page)

    async def pick_datetime(self, page, picker, target, timeout):
        header = picker.locator('[data-testid="beast-core-datePicker-dropdown-header"]')
        # Read the displayed year AND month. Never guess a year from today's date.
        for _ in range(36):
            text = await header.inner_text(timeout=timeout)
            match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月", text)
            if not match:
                raise RuntimeError("无法确认拼多多日历年月，已停止定时设置")
            year, month = map(int, match.groups())
            if (year, month) == (target.year, target.month):
                break
            direction = "right" if (year, month) < (target.year, target.month) else "left"
            await header.locator(f'[data-testid="beast-core-icon-{direction}"]').click(timeout=timeout)
            # Wait for actual navigation, rather than repeatedly clicking stale headers.
            deadline = time.monotonic() + timeout / 1000
            while await header.inner_text() == text:
                if time.monotonic() >= deadline:
                    raise RuntimeError("拼多多日历未翻月，已停止定时设置")
                await asyncio.sleep(0.1)
        else:
            raise ValueError("拼多多目标月份超出本次日历导航范围")
        days = picker.locator('table[data-testid="beast-core-datePicker-table"] td').filter(
            has_text=re.compile(r"^\s*" + str(target.day) + r"\s*$")
        )
        valid = []
        for day in await days.all():
            classes = await day.get_attribute("class") or ""
            if not re.search(r"disabled|outOfMonth", classes, re.I) and await day.get_attribute("aria-disabled") != "true":
                valid.append(day)
        if len(valid) != 1:
            raise ValueError("拼多多目标日期不可选或不唯一，未改成立即发布")
        await valid[0].click(timeout=timeout)
        await picker.locator('input[data-testid="beast-core-timePicker-html-input"]').click(timeout=timeout)
        columns = page.locator('ul[class*="TPK_ul"]:visible')
        if await columns.count() != 3:
            raise RuntimeError("拼多多时分秒控件未完整显示，已停止定时设置")
        for index, value in enumerate((target.hour, target.minute, target.second)):
            item = columns.nth(index).locator('li[class*="cIL_item"]').filter(
                has_text=re.compile(r"^\s*" + f"{value:02d}" + r"\s*$")
            )
            if await item.count() != 1 or re.search(r"disabled", await item.get_attribute("class") or "", re.I) or await item.get_attribute("aria-disabled") == "true":
                raise ValueError("拼多多目标时间不可选，已停止定时设置")
            await item.click(timeout=timeout)

    async def verify_schedule(self, page):
        label = "定时发布" if self.publish_date is not None else "立即发布"
        if not await self.mode_checked(page, label):
            raise RuntimeError("拼多多发布方式与请求不一致，已停止发布")
        if self.publish_date is None:
            return
        target = normalize_publish_date(self.publish_date)
        date = page.locator(DATE_INPUT).locator("visible=true")
        if await date.count() != 1 or await date.input_value() != target.strftime("%Y-%m-%d %H:%M:%S"):
            raise RuntimeError("拼多多页面定时时间与请求不一致，已停止发布")
        if await page.locator(PICKER).count() or await date.get_attribute("aria-invalid") == "true":
            raise RuntimeError("拼多多定时时间未通过页面确认，已停止发布")

    async def submit(self, page, timeout=PROCESSING_TIMEOUT):
        await self.verify_declaration(page)
        await self.verify_schedule(page)
        if await page.locator('[aria-invalid="true"]:visible').count():
            raise RuntimeError("拼多多表单存在校验错误，未提交发布")
        button = page.get_by_role("button", name="发布", exact=True).locator("visible=true")
        if await button.count() == 0:
            button = page.get_by_role("button", name="一键发布", exact=True).locator("visible=true")
        if await button.count() != 1 or not await button.is_enabled():
            raise RuntimeError("拼多多发布按钮不可用或不唯一，未提交；请检查封面及表单必填项")
        if self.dry_run:
            pdd_logger.info("拼多多试运行：表单已填写，未点击发布")
            return {"status": "prepared", "published": False, "dryRun": True}
        # Reject stale success before clicking, so it cannot prove this upload.
        success = page.get_by_text(re.compile(r"^(?:视频)?(?:发布成功|提交成功|定时发布成功)[！!。]?$"))
        if await success.locator("visible=true").count():
            raise RuntimeError("拼多多页面残留成功提示，无法确认本次发布")
        await button.click(timeout=30000)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            failure = page.get_by_text(re.compile(r"发布失败|提交失败|请重新登录|定时时间.*(?:无效|错误)"))
            if await failure.locator("visible=true").count():
                raise RuntimeError("拼多多页面报告发布失败，请检查页面提示")
            if await success.locator("visible=true").count():
                return {"status": "scheduled" if self.publish_date else "published",
                        "published": self.publish_date is None, "dryRun": False}
            await asyncio.sleep(0.25)
        raise TimeoutError("拼多多已点击发布，但结果未确认；请先检查内容列表，不要直接重发")

    async def upload(self, playwright):
        if not self.file_path.is_file():
            raise FileNotFoundError("拼多多待发布视频不存在")
        browser = await playwright.chromium.launch(**chromium_launch_options(False))
        context = None
        try:
            options = {"viewport": {"width": 1440, "height": 1100}}
            if self.account_file.is_file():
                options["storage_state"] = self.account_file
            context = await browser.new_context(**options)
            page = await context.new_page()
            await page.goto(PDD_PUBLISH_URL, wait_until="domcontentloaded", timeout=120000)
            if not await logged_in(page, context):
                pdd_logger.info("等待拼多多个人账号登录，成功后继续本次任务")
                await wait_for_login(page, context)
            await save_session(context, self.account_file)
            await page.locator(VIDEO_INPUT).set_input_files(str(self.file_path), timeout=PROCESSING_TIMEOUT * 1000)
            await self.wait_upload(page)
            await page.locator('div.sabo-root[contenteditable="true"]').fill(self.caption, timeout=30000)
            await self.set_declaration(page)
            await self.set_schedule(page)
            result = await self.submit(page)
            try:
                await save_session(context, self.account_file)
            except Exception:
                pdd_logger.warning("拼多多任务已完成，但登录态刷新失败；不自动重发")
            return result
        finally:
            await close_browser(context, browser)

    async def main(self):
        async with async_playwright() as playwright:
            return await self.upload(playwright)
