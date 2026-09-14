import asyncio
from pathlib import Path
from datetime import datetime
from conf import BASE_DIR
from uploader.douyin_uploader.main import DouYinVideo
from uploader.ks_uploader.main import KSVideo
from uploader.tencent_uploader.main import TencentVideo
from uploader.xiaohongshu_uploader.main import XiaoHongShuVideo
from utils.constant import TencentZoneTypes
from uploader.tk_uploader.main import TiktokVideo
from uploader.youtube_uploader.main import YouTubeVideo


def post_video_tencent(title,files,tags,account_file,category=TencentZoneTypes.LIFESTYLE.value,enableTimer=False,videos_per_day = 1, daily_times=None,start_days = 0,endpublishTime=''):
    # 生成文件的完整路径
    account_file = [Path(BASE_DIR / "cookiesFile" / file) for file in account_file]
    files = [Path(BASE_DIR / "videoFile" / file) for file in files]
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
    account_file = [Path(BASE_DIR / "cookiesFile" / file) for file in account_file]
    files = [Path(BASE_DIR / "videoFile" / file) for file in files]
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
    account_file = [Path(BASE_DIR / "cookiesFile" / file) for file in account_file]
    files = [Path(BASE_DIR / "videoFile" / file) for file in files]
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
    account_file = [Path(BASE_DIR / "cookiesFile" / file) for file in account_file]
    files = [Path(BASE_DIR / "videoFile" / file) for file in files]
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

def post_video_tk(title,files,tags,account_file,category=TencentZoneTypes.LIFESTYLE.value,enableTimer=False,videos_per_day = 1, daily_times=None,start_days = 0,endpublishTime=''):
    # 生成文件的完整路径
    account_file = [Path(BASE_DIR / "cookiesFile" / file) for file in account_file]
    files = [Path(BASE_DIR / "videoFile" / file) for file in files]
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
            app = TiktokVideo(title, str(file), tags, publish_datetimes, cookie,enableTimer)
            asyncio.run(app.main(), debug=False)
def post_video_youtube(title,files,tags,account_file,category=TencentZoneTypes.LIFESTYLE.value,enableTimer=False,videos_per_day = 1, daily_times=None,start_days = 0,endpublishTime=''):
    # 生成文件的完整路径
    account_file = [Path(BASE_DIR / "cookiesFile" / file) for file in account_file]
    files = [Path(BASE_DIR / "videoFile" / file) for file in files]
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
            app = YouTubeVideo(title, str(file), tags, publish_datetimes, cookie,enableTimer)
            asyncio.run(app.main(), debug=False)


def parse_publish_date(publish_date_str: str) -> datetime:
    """解析 'YYYY年M月D日 HH:MM:SS' 返回 datetime 对象"""
    #publish_date_str='2025-11-26 12:00:00'
    publish_date_str = f'{publish_date_str}'.replace('T', ' ').replace('.000+00:00', '').strip()
    print(publish_date_str)
    return datetime.strptime(publish_date_str, '%Y-%m-%d %H:%M:%S')

def format_publish_date_str(publish_date_str: str) -> str:
    """将 'YYYY年M月D日 HH:MM' 转为 'YYYY-MM-DD HH:MM:SS' 字符串"""
    dt = datetime.strptime(publish_date_str.strip(), '%Y年%m月%d日 %H:%M')
    return dt.strftime('%Y-%m-%d %H:%M:%S')
