# Unreleased

- 修正 Instagram 网页发布入口、首次 Reels 提示、“继续”按钮和富文本说明框；TikTok 改为等待视频输入框，支持中文上传/发布界面，并在失败时关闭发布浏览器。
- 补齐 `POST /uploadFromUrl` 本机视频下载接口与 CORS 预检，修复网页发布时显示的跨域错误。
- 按本机发布工作流的兼容要求，`/uploadFromUrl` 下载 HTTPS 视频时忽略证书校验错误，但仍阻止私网地址并限制文件大小。
- 账号列表的 Cookie 实时验证仅保留视频号，其他平台不再因列表刷新启动浏览器检查。
- X、Instagram 和 Facebook 改为本机 Chrome 登录与网页发布，移除官方 API 凭据导入。
- X、Instagram 和 Facebook 的首次登录改用普通 Chrome 独立资料目录，修复使用 Google 账号登录时反复进入“重试”页。
- TikTok 首次登录也改用普通 Chrome 独立资料目录，修复选择 Google 登录时提示浏览器不受支持的问题，同时保留历史 JSON 登录态兼容。
- TikTok、YouTube、X、Instagram 和 Facebook 在普通 Chrome 登录完成时导出独立会话文件，修复 macOS 系统钥匙串与自动化浏览器模拟钥匙串不兼容、导致发布时登录态消失的问题。
- YouTube、X、Instagram 和 Facebook 改用必需 Cookie 名称确认登录完成，修复 Chrome 历史被锁定时账号不保存，以及仅访问首页就被误判为已登录的问题。
- X、Instagram、Facebook 和 TikTok 发布补齐正文字段传递。
- 新增支付宝生活号浏览器登录、视频发布、封面和合集选择。
- 迁移 TikTok 新版 Studio 上传页选择器，支持封面上传，并保留正确的 5 分钟定时取整。
- YouTube 发布接口补齐简介、封面、播放列表与可见性参数。
- TikTok 和 YouTube 新增本机浏览器登录入口，并修复真实发布时的参数错误。
- YouTube 首次登录改用普通 Chrome 独立资料目录，避免 Google 拒绝自动化浏览器登录。
- 不支持原生定时的平台收到定时请求时自动改为立即发布，不再报错。
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
