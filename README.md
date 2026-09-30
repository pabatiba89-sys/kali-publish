# Kali Publish

Kali Publish 是本地运行的多平台视频发布后端，通过本机 Chrome 保存各平台登录态，支持视频上传和网页自动发布。定时发布只在已适配平台开放。

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
| 10 | 支付宝生活号 | 浏览器登录 | 是 | 否 |

所有平台都通过 `/login` 添加账号，不再需要开发者 API 令牌。YouTube、X、Instagram 和 Facebook 的首次登录使用完全普通的 Chrome 窗口和各自独立的资料目录，因此通过 Google 账号登录时不会进入“浏览器不安全”的重试页。后续发布仅复用对应专用登录态。Facebook 会发布到登录窗口中当前选中的身份；如果要发到主页，登录时先切换到对应主页身份。

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

### 登录账号

例如添加 X 账号：

```text
GET /login?type=7&id=brand-x
```

返回 `browser_opened` 后，在弹出的 Chrome 窗口中登录，并保持窗口打开直到服务返回 `200`，此时账号才已保存。其他平台只需替换 `type`。YouTube、X、Instagram 和 Facebook 会通过专用 Chrome 资料中必需的 Cookie 名称确认登录完成，不依赖可能被锁定或误判的浏览历史，也不读取 Cookie 内容。登录态保存在数据目录的 `cookiesFile/`，不会读取日常 Chrome 资料；删除账号时会一并删除对应登录态。

X、Instagram、Facebook 和 TikTok 可传 `description` 或 `content`；YouTube 还可传 `description`、`thumbnailPath`、`playlist`、`visibility`；TikTok 可传 `thumbnailPath`；支付宝生活号可传 `description`、`thumbnailPath`、`collectionName`。封面文件需要先通过 `/upload` 上传，并传入返回的 `filepath`。

## 数据与配置

- macOS 数据目录：`~/Library/Application Support/Kali Publish/`
- Windows 数据目录：`%LOCALAPPDATA%\Kali Publish\`
- `KALI_PUBLISH_DATA_DIR`：自定义数据目录
- `LOCAL_CHROME_PATH`：指定 Google Chrome 路径
- `LOCAL_CHROME_HEADLESS`：控制浏览器是否无界面运行
- `HOST`、`PORT`：修改监听地址和端口

服务默认只监听 `127.0.0.1:5409`，不应直接暴露到公网，因为它没有用户认证且可接收发布凭据。发布包未进行商业代码签名，首次运行可能出现系统安全提示。
