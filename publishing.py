from myUtils.postVideo import (
    post_video_DouYin,
    post_video_ks,
    post_video_tencent,
    post_video_tk,
    post_video_xhs,
    post_video_youtube,
)


PLATFORMS = {
    1: {"name": "小红书", "publisher": post_video_xhs, "login": True},
    2: {"name": "视频号", "publisher": post_video_tencent, "login": True},
    3: {"name": "抖音", "publisher": post_video_DouYin, "login": True},
    4: {"name": "快手", "publisher": post_video_ks, "login": True},
    5: {"name": "TikTok", "publisher": post_video_tk, "login": False},
    6: {"name": "YouTube", "publisher": post_video_youtube, "login": False},
}


def publish_videos(payload: dict) -> None:
    platform_type = int(payload["type"])
    platform = PLATFORMS.get(platform_type)
    if platform is None:
        raise ValueError(f"Unsupported platform type: {platform_type}")

    file_list = payload.get("fileList") or []
    account_list = payload.get("accountList") or []
    if not file_list:
        raise ValueError("fileList must not be empty")
    if not account_list:
        raise ValueError("accountList must not be empty")

    category = payload.get("category")
    if category == 0:
        category = None
    enable_timer = payload.get("sendnow", "schedule") == "schedule"
    arguments = [
        payload.get("title") or "",
        file_list,
        payload.get("tags") or [],
        account_list,
        category,
        enable_timer,
        int(payload.get("videosPerDay", 1)),
        payload.get("dailyTimes") or None,
        int(payload.get("startDays", 0)),
    ]
    end_publish_time = payload.get("endpublishTime", "")

    if platform_type == 3:
        platform["publisher"](
            *arguments,
            payload.get("productLink", ""),
            payload.get("productTitle", ""),
            end_publish_time,
        )
    else:
        platform["publisher"](*arguments, end_publish_time)
