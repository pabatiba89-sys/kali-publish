from myUtils.postVideo import (
    post_video_alipay,
    post_video_facebook,
    post_video_instagram,
    post_video_DouYin,
    post_video_ks,
    post_video_tencent,
    post_video_tk,
    post_video_x,
    post_video_xhs,
    post_video_youtube,
)


PLATFORMS = {
    1: {
        "name": "小红书", "publisher": post_video_xhs, "login": True,
        "accountMode": "browser", "supportsSchedule": True,
    },
    2: {
        "name": "视频号", "publisher": post_video_tencent, "login": True,
        "accountMode": "browser", "supportsSchedule": True,
    },
    3: {
        "name": "抖音", "publisher": post_video_DouYin, "login": True,
        "accountMode": "browser", "supportsSchedule": True,
    },
    4: {
        "name": "快手", "publisher": post_video_ks, "login": True,
        "accountMode": "browser", "supportsSchedule": True,
    },
    5: {
        "name": "TikTok", "publisher": post_video_tk, "login": True,
        "accountMode": "browser", "supportsSchedule": True,
    },
    6: {
        "name": "YouTube", "publisher": post_video_youtube, "login": True,
        "accountMode": "browser", "supportsSchedule": False,
    },
    7: {
        "name": "X", "publisher": post_video_x, "login": True,
        "accountMode": "browser", "supportsSchedule": False,
    },
    8: {
        "name": "Instagram", "publisher": post_video_instagram, "login": True,
        "accountMode": "browser", "supportsSchedule": False,
    },
    9: {
        "name": "Facebook", "publisher": post_video_facebook, "login": True,
        "accountMode": "browser", "supportsSchedule": False,
    },
    10: {
        "name": "支付宝生活号", "publisher": post_video_alipay, "login": True,
        "accountMode": "browser", "supportsSchedule": False,
    },
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
    enable_timer = payload.get("sendnow", "now") == "schedule"
    if enable_timer and not platform.get("supportsSchedule", True):
        raise ValueError(f"{platform['name']} does not support scheduled publishing")
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
    elif platform_type == 5:
        platform["publisher"](
            *arguments,
            end_publish_time,
            payload.get("thumbnailPath") or payload.get("thumbnail"),
        )
    elif platform_type == 6:
        platform["publisher"](
            *arguments,
            end_publish_time,
            payload.get("description", ""),
            payload.get("thumbnailPath") or payload.get("thumbnail"),
            payload.get("playlist"),
            payload.get("visibility", "public"),
        )
    elif platform_type == 10:
        platform["publisher"](
            *arguments,
            end_publish_time,
            payload.get("description", ""),
            payload.get("thumbnailPath") or payload.get("thumbnail"),
            payload.get("collectionName"),
        )
    else:
        platform["publisher"](*arguments, end_publish_time)
