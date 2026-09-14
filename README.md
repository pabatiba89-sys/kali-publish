# Kali Publish

Kali Publish 是本地运行的多平台视频发布后端，支持账号登录、视频上传、立即发布和定时发布。

## 支持平台

| Type | 平台 | API 登录 | 视频发布 |
|---:|---|:---:|:---:|
| 1 | 小红书 | 是 | 是 |
| 2 | 视频号 | 是 | 是 |
| 3 | 抖音 | 是 | 是 |
| 4 | 快手 | 是 | 是 |
| 5 | TikTok | 否 | 是 |
| 6 | YouTube | 否 | 是 |

TikTok 和 YouTube 需要预先准备兼容的浏览器登录态文件。

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
2. 通过登录接口添加发布账号，或放入已有的浏览器登录态文件。
3. 上传待发布视频。
4. 调用单次发布或批量发布接口，选择平台、账号和发布时间。

## API

- `GET /health`：检查服务状态
- `GET /api/platforms`：获取支持的平台
- `POST /upload`：上传视频
- `GET /getFiles`：获取已上传视频
- `DELETE /deleteFile`：删除视频
- `GET /login`：登录小红书、视频号、抖音或快手账号
- `GET /getAccounts`：获取发布账号
- `GET /getValidAccounts`：检查账号登录状态
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

服务默认只监听 `127.0.0.1:5409`，不应直接暴露到公网。发布包未进行商业代码签名，首次运行可能出现系统安全提示。
