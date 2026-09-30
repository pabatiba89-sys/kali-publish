# Unreleased

- 新增 X、Instagram 和 Facebook 视频自动发布。
- X 使用官方 v2 分片上传与发布接口。
- Instagram 使用 Meta 官方 Reels 可恢复上传；Facebook 使用主页 Reels 发布接口。
- TikTok 和 YouTube 新增本机浏览器登录入口，并修复真实发布时的参数错误。
- YouTube 首次登录改用普通 Chrome 独立资料目录，避免 Google 拒绝自动化浏览器登录。
- 同步视频号最新发布规则：追加业务话题和账号提及，并处理新版内容标记选项。

# Kali Publish v1.0.0

首个公开发行版，用于在本机统一发布多平台视频。

## 包含内容

- macOS 15 Apple Silicon（arm64）版本
- Windows 2025 x64 版本
- 内置 Python 与 Playwright 运行时
- 小红书、视频号、抖音、快手、TikTok、YouTube 发布适配器
- 本地账号、登录态、视频文件和批量发布 API

## 使用提醒

- 两个平台的可执行文件均未进行商业代码签名，首次运行可能出现系统安全提示。
- 所有平台均使用本机安装的 Google Chrome；如未安装，浏览器发布功能无法运行。
- 服务默认监听 `127.0.0.1:5409`，没有公网用户认证，不要直接暴露到互联网。
- 压缩包对应的 `.sha256` 文件用于校验下载完整性。
