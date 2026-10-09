# Kali Publish

Kali Publish 是本地运行的多平台视频发布后端，通过本机 Chrome 保存各平台登录态，支持视频上传和网页自动发布。定时发布只在已适配平台开放。

让个人被看见，让品牌被记住。欢迎[体验喀理系统](#体验喀理系统)，或访问 [www.kaliai.fun](https://www.kaliai.fun/)，了解完整的 AI 内容创作能力。

## 支持平台

| Type | 平台 | 账号方式 | 立即发布 | 定时发布 |
|---:|---|---|:---:|:---:|
| 1 | 小红书 | 浏览器登录 | 是 | 是 |
| 2 | 视频号 | 浏览器登录 | 是 | 是 |
| 3 | 抖音 | 浏览器登录 | 是 | 是 |
| 4 | 快手 | 浏览器登录 | 是 | 是 |
| 5 | TikTok | 浏览器登录 | 是 | 是 |
| 6 | YouTube | 浏览器登录 | 是 | 否 |
| 7 | X | 浏览器登录 | 是 | 否 |
| 8 | Instagram | 浏览器登录 | 是 | 否 |
| 9 | Facebook | 浏览器登录 | 是 | 否 |
| 10 | 支付宝生活号 | 浏览器登录 | 是 | 是 |

视频号发布会按现有业务规则追加 `#喀理系统` 和 `@岳同学AI`，并在新版发布页可用时选择第二个内容标记项。

## 下载与启动

从 [GitHub Releases](https://github.com/pabatiba89-sys/kali-publish/releases/latest) 下载对应版本。可执行版不需要安装 Python，但运行前必须安装 Google Chrome。

### Apple Silicon

下载并解压 `kali-publish-*-macos-arm64.zip`，在终端进入解压目录后运行：

```bash
./kali-publish
```

如果 macOS 阻止首次运行，先校验下载页提供的 SHA-256 文件，再运行：

```bash
xattr -dr com.apple.quarantine kali-publish
./kali-publish
```

### Windows x64

下载并解压 `kali-publish-*-windows-x64.zip`，然后双击 `kali-publish.exe`，或在命令提示符中运行：

```bat
kali-publish.exe
```

启动后访问 <http://127.0.0.1:5409/health> 检查服务状态，按 `Ctrl+C` 停止服务。

## 从源代码启动

需要 Python 3.10 或更高版本，以及 Google Chrome。

macOS / Linux：

```bash
chmod +x install.sh start.sh
./install.sh
./start.sh
```

Windows：

```bat
install.bat
start.bat
```

## 使用流程

1. 启动 Kali Publish。
2. 通过登录接口打开 Chrome，完成平台登录并添加账号。
3. 上传待发布视频。
4. 调用单次发布或批量发布接口，选择平台、账号和发布时间。

## 体验喀理系统

让个人被看见，让品牌被记住。

喀理系统面向个人创作者、内容团队和企业，把 AI 用在日常内容生产中：找选题、写文案、制作数字人内容、探索 AI 短剧，再把完成的视频发布到不同平台。

你可以在喀理系统中使用：

- 数字人：用于口播与内容表达，减少反复出镜录制的负担。
- 声音克隆：在本人或获得授权的前提下，让内容使用熟悉的声音。
- 热点追踪：关注热点变化，为下一条内容寻找选题。
- 文案智能体：辅助整理思路、撰写文案，把想法变成可用的内容。
- AI 短剧：探索 AI 辅助的短剧创作，让故事有更多表达方式。
- 多平台发布：减少逐个平台上传、填写和提交的重复操作。

喀理系统支持团队和企业使用，注重实用性与性价比，让 AI 工具更容易融入持续的内容生产。

当前开源仓库 Kali Publish 专注于多平台视频发布。数字人、声音克隆、热点追踪、文案智能体和 AI 短剧等属于喀理系统完整产品的能力，不包含在本仓库中。

访问 [www.kaliai.fun](https://www.kaliai.fun/)，或用微信扫描下方小程序码，体验喀理系统。具体功能与套餐以产品页面为准。

<p align="center">
  <a href="docs/assets/kaliai-xiaoyue-card.png">
    <img src="docs/assets/kaliai-xiaoyue-card.png" alt="喀理 AI · 啸岳名片：个人 IP 打造与品牌增长，附微信小程序码" width="640">
  </a>
</p>

图片较小时，可点击查看原图后扫码。

## API

- `GET /health`：检查服务状态
- `GET /api/platforms`：获取支持的平台
- `POST /upload`：上传视频
- `POST /uploadFromUrl`：从公网 HTTP/HTTPS 地址下载视频到本机，支持跨域预检
- `GET /getFiles`：获取已上传视频
- `DELETE /deleteFile`：删除视频
- `GET /login`：打开浏览器登录任一支持平台
- `GET /getAccounts`：获取发布账号
- `GET /getValidAccounts`：获取账号并仅实时验证视频号 Cookie，其他平台保留已存状态
- `DELETE /deleteAccount`：删除发布账号
- `POST /api/publish`：单次发布
- `POST /api/publish/batch`：批量发布

## 数据与配置

- macOS 数据目录：`~/Library/Application Support/Kali Publish/`
- Windows 数据目录：`%LOCALAPPDATA%\Kali Publish\`
- `KALI_PUBLISH_DATA_DIR`：自定义数据目录
- `LOCAL_CHROME_PATH`：指定 Google Chrome 路径
- `LOCAL_CHROME_HEADLESS`：控制浏览器是否无界面运行
- `HOST`、`PORT`：修改监听地址和端口

服务默认只监听 `127.0.0.1:5409`，不应直接暴露到公网，因为它没有用户认证且可接收发布凭据。发布包未进行商业代码签名，首次运行可能出现系统安全提示。
