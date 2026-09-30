import asyncio
from pathlib import Path
from datetime import datetime
from conf import COOKIES_FOLDER, VIDEO_FOLDER
from uploader.douyin_uploader.main import DouYinVideo
from uploader.ks_uploader.main import KSVideo
from uploader.tencent_uploader.main import TencentVideo
from uploader.xiaohongshu_uploader.main import XiaoHongShuVideo
from utils.constant import TencentZoneTypes
from uploader.tk_uploader.main import TiktokVideo
from uploader.youtube_uploader.main import YouTubeVideo
from uploader.alipay_uploader.main import AlipayVideo
from uploader.web_publishers import (
    FacebookWebVideo,
    InstagramWebVideo,
    XWebVideo,
)


def post_video_tencent(title,files,tags,account_file,category=TencentZoneTypes.LIFESTYLE.value,enableTimer=False,videos_per_day = 1, daily_times=None,start_days = 0,endpublishTime=''):
    # 生成文件的完整路径
    account_file = [Path(COOKIES_FOLDER / file) for file in account_file]
    files = [Path(VIDEO_FOLDER / file) for file in files]
    if enableTimer:
        endpublishTime = parse_publish_date(endpublishTime)

    for index, file in enumerate(files):
        for cookie in account_file:
            print(f"文件路径{str(file)}")
            # 打印视频文件名、标题和 hashtag
            print(f"视频文件名：{file}")
            print(f"标题：{title}")
            print(f"Hashtag：{tags}")
            app = TencentVideo(title, str(file), tags, endpublishTime, cookie, category,enableTimer)
            asyncio.run(app.main(), debug=False)


def post_video_DouYin(title,files,tags,account_file,category=TencentZoneTypes.LIFESTYLE.value,enableTimer=False,videos_per_day = 1, daily_times=None,start_days = 0,
                      productLink = '', productTitle = '',endpublishTime=''):
    # 生成文件的完整路径
    account_file = [Path(COOKIES_FOLDER / file) for file in account_file]
    files = [Path(VIDEO_FOLDER / file) for file in files]
    publish_datetimes = None
    if enableTimer:
        publish_datetimes = parse_publish_date(endpublishTime)

    for index, file in enumerate(files):
        for cookie in account_file:
            print(f"文件路径{str(file)}")
            # 打印视频文件名、标题和 hashtag
            print(f"视频文件名：{file}")
            print(f"标题：{title}")
            print(f"Hashtag：{tags}")
            app = DouYinVideo(title, str(file), tags, publish_datetimes, cookie, category, productLink, productTitle,enableTimer)
            asyncio.run(app.main(), debug=False)


def post_video_ks(title,files,tags,account_file,category=TencentZoneTypes.LIFESTYLE.value,enableTimer=False,videos_per_day = 1, daily_times=None,start_days = 0,endpublishTime=''):
    # 生成文件的完整路径
    account_file = [Path(COOKIES_FOLDER / file) for file in account_file]
    files = [Path(VIDEO_FOLDER / file) for file in files]
    publish_datetimes = None
    if enableTimer:
        publish_datetimes = parse_publish_date(endpublishTime)

    for index, file in enumerate(files):
        for cookie in account_file:
            print(f"文件路径{str(file)}")
            # 打印视频文件名、标题和 hashtag
            print(f"视频文件名：{file}")
            print(f"标题：{title}")
            print(f"Hashtag：{tags}")
            app = KSVideo(title, str(file), tags, publish_datetimes, cookie,enableTimer)
            asyncio.run(app.main(), debug=False)

def post_video_xhs(title,files,tags,account_file,category=TencentZoneTypes.LIFESTYLE.value,enableTimer=False,videos_per_day = 1, daily_times=None,start_days = 0,endpublishTime=''):
    # 生成文件的完整路径
    account_file = [Path(COOKIES_FOLDER / file) for file in account_file]
    files = [Path(VIDEO_FOLDER / file) for file in files]
    file_num = len(files)
    publish_datetimes = None
    if enableTimer:
        publish_datetimes = parse_publish_date(endpublishTime)
        #publish_datetimes = parse_publish_date('2025-11-27 12:00:00')

    for index, file in enumerate(files):
        for cookie in account_file:
            # 打印视频文件名、标题和 hashtag
            print(f"视频文件名：{file}")
            print(f"标题：{title}")
            print(f"Hashtag：{tags}")
            app = XiaoHongShuVideo(title, file, tags, publish_datetimes, cookie,enableTimer)
            asyncio.run(app.main(), debug=False)

def _optional_video_asset(filename):
    if not filename:
        return None
    path = Path(str(filename))
    if path.name != str(filename):
        raise ValueError("asset filename must not contain a directory")
    return Path(VIDEO_FOLDER / path.name)


def post_video_tk(title,files,tags,account_file,category=TencentZoneTypes.LIFESTYLE.value,enableTimer=False,videos_per_day = 1, daily_times=None,start_days = 0,endpublishTime='', thumbnail_path=None):
    # 生成文件的完整路径
    account_file = [Path(COOKIES_FOLDER / file) for file in account_file]
    files = [Path(VIDEO_FOLDER / file) for file in files]
    file_num = len(files)
    publish_datetimes = None
    if enableTimer:
        publish_datetimes = parse_publish_date(endpublishTime)
        #publish_datetimes = parse_publish_date('2025-11-27 12:00:00')

    for index, file in enumerate(files):
        for cookie in account_file:
            # 打印视频文件名、标题和 hashtag
            print(f"视频文件名：{file}")
            print(f"标题：{title}")
            print(f"Hashtag：{tags}")
            app = TiktokVideo(
                title,
                str(file),
                tags,
                publish_datetimes or 0,
                cookie,
                thumbnail_path=_optional_video_asset(thumbnail_path),
            )
            asyncio.run(app.main(), debug=False)
def post_video_youtube(title,files,tags,account_file,category=TencentZoneTypes.LIFESTYLE.value,enableTimer=False,videos_per_day = 1, daily_times=None,start_days = 0,endpublishTime='', description='', thumbnail_path=None, playlist=None, visibility='public'):
    # 生成文件的完整路径
    account_file = [Path(COOKIES_FOLDER / file) for file in account_file]
    files = [Path(VIDEO_FOLDER / file) for file in files]
    publish_datetimes = None
    if enableTimer:
        publish_datetimes = parse_publish_date(endpublishTime)
        #publish_datetimes = parse_publish_date('2025-11-27 12:00:00')

    for index, file in enumerate(files):
        for cookie in account_file:
            # 打印视频文件名、标题和 hashtag
            print(f"视频文件名：{file}")
            print(f"标题：{title}")
            print(f"Hashtag：{tags}")
            app = YouTubeVideo(
                title,
                str(file),
                tags,
                cookie,
                description=description,
                thumbnail_path=_optional_video_asset(thumbnail_path),
                playlist=playlist,
                visibility=visibility,
            )
            asyncio.run(app.main(), debug=False)


def _post_with_browser_uploader(
    publisher_class,
    title,
    files,
    tags,
    account_file,
):
    account_paths = [Path(COOKIES_FOLDER / file) for file in account_file]
    video_paths = [Path(VIDEO_FOLDER / file) for file in files]
    for video_path in video_paths:
        for account_path in account_paths:
            publisher = publisher_class(title, video_path, tags, account_path)
            asyncio.run(publisher.main(), debug=False)


def post_video_x(title, files, tags, account_file, category=None, enableTimer=False,
                 videos_per_day=1, daily_times=None, start_days=0, endpublishTime=''):
    _post_with_browser_uploader(XWebVideo, title, files, tags, account_file)


def post_video_instagram(title, files, tags, account_file, category=None, enableTimer=False,
                         videos_per_day=1, daily_times=None, start_days=0, endpublishTime=''):
    _post_with_browser_uploader(InstagramWebVideo, title, files, tags, account_file)


def post_video_facebook(title, files, tags, account_file, category=None, enableTimer=False,
                        videos_per_day=1, daily_times=None, start_days=0, endpublishTime=''):
    _post_with_browser_uploader(FacebookWebVideo, title, files, tags, account_file)


def post_video_alipay(title, files, tags, account_file, category=None, enableTimer=False,
                      videos_per_day=1, daily_times=None, start_days=0, endpublishTime='',
                      description='', thumbnail_path=None, collection_name=None):
    account_paths = [Path(COOKIES_FOLDER / file) for file in account_file]
    video_paths = [Path(VIDEO_FOLDER / file) for file in files]
    for video_path in video_paths:
        for account_path in account_paths:
            publisher = AlipayVideo(
                title,
                video_path,
                tags,
                account_path,
                desc=description,
                thumbnail_path=_optional_video_asset(thumbnail_path),
                collection_name=collection_name,
            )
            asyncio.run(publisher.main(), debug=False)


def parse_publish_date(publish_date_str: str) -> datetime:
    """Parse an ISO-style timestamp and normalize aware values to local wall time."""
    value = str(publish_date_str).strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed

def format_publish_date_str(publish_date_str: str) -> str:
    """将 'YYYY年M月D日 HH:MM' 转为 'YYYY-MM-DD HH:MM:SS' 字符串"""
    dt = datetime.strptime(publish_date_str.strip(), '%Y年%m月%d日 %H:%M')
    return dt.strftime('%Y-%m-%d %H:%M:%S')
