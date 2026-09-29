# Kali Publish

Kali Publish 是本地运行的多平台视频发布后端，支持账号登录或 API 凭据导入、视频上传和自动发布。定时发布只在平台原生接口支持时开放。

## 支持平台

| Type | 平台 | 账号方式 | 立即发布 | 定时发布 |
|---:|---|---|:---:|:---:|
| 1 | 小红书 | 浏览器登录 | 是 | 是 |
| 2 | 视频号 | 浏览器登录 | 是 | 是 |
| 3 | 抖音 | 浏览器登录 | 是 | 是 |
| 4 | 快手 | 浏览器登录 | 是 | 是 |
| 5 | TikTok | 浏览器登录 | 是 | 是 |
| 6 | YouTube | 浏览器登录 | 是 | 否 |
| 7 | X | OAuth 2.0 用户令牌 | 是 | 否 |
| 8 | Instagram | Meta 用户令牌 | 是 | 否 |
| 9 | Facebook | Facebook 主页令牌 | 是 | 是 |

TikTok 和 YouTube 可通过 `/login` 打开本机 Chrome 完成登录。X、Instagram 和 Facebook 走官方 API，通过 `/api/accounts/import` 导入凭据，不使用网页点击脚本。

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
2. 通过登录接口添加浏览器账号，或通过凭据导入接口添加官方 API 账号。
3. 上传待发布视频。
4. 调用单次发布或批量发布接口，选择平台、账号和发布时间。

## API

- `GET /health`：检查服务状态
- `GET /api/platforms`：获取支持的平台
- `POST /upload`：上传视频
- `GET /getFiles`：获取已上传视频
- `DELETE /deleteFile`：删除视频
- `GET /login`：登录小红书、视频号、抖音、快手、TikTok 或 YouTube 账号
- `POST /api/accounts/import`：导入 X、Instagram 或 Facebook 的 API 凭据
- `GET /getAccounts`：获取发布账号
- `GET /getValidAccounts`：检查浏览器登录态或 API 凭据文件格式
- `DELETE /deleteAccount`：删除发布账号
- `POST /api/publish`：单次发布
- `POST /api/publish/batch`：批量发布

### 导入 X、Instagram 和 Facebook 账号

请只把凭据发给本机 `127.0.0.1` 服务。以下值均为占位符：

```json
{
  "type": 7,
  "userName": "brand-x",
  "credentials": {
    "access_token": "<X OAuth 2.0 user access token>"
  }
}
```

```json
{
  "type": 8,
  "userName": "brand-instagram",
  "credentials": {
    "access_token": "<Meta user access token>",
    "ig_user_id": "<Instagram professional account id>",
    "graph_api_version": "v25.0"
  }
}
```

```json
{
  "type": 9,
  "userName": "brand-facebook",
  "credentials": {
    "access_token": "<Facebook Page access token>",
    "page_id": "<Facebook Page id>",
    "graph_api_version": "v25.0"
  }
}
```

- X 需要已开通付费额度的开发者应用，令牌至少要有 `tweet.write`、`media.write` 和 `users.read` 权限。
- Instagram 需要专业账号、Facebook Login for Business 以及 `instagram_basic`、`instagram_content_publish` 权限。
- Facebook 只发布到主页，需要 `pages_show_list`、`pages_read_engagement`、`pages_manage_posts` 权限。
- API 凭据保存在数据目录的 `cookiesFile/` 中，文件权限设为仅当前用户可读写；删除账号时会一并删除凭据文件。

## 数据与配置

- macOS 数据目录：`~/Library/Application Support/Kali Publish/`
- Windows 数据目录：`%LOCALAPPDATA%\Kali Publish\`
- `KALI_PUBLISH_DATA_DIR`：自定义数据目录
- `LOCAL_CHROME_PATH`：指定 Google Chrome 路径
- `LOCAL_CHROME_HEADLESS`：控制浏览器是否无界面运行
- `HOST`、`PORT`：修改监听地址和端口

服务默认只监听 `127.0.0.1:5409`，不应直接暴露到公网，因为它没有用户认证且可接收发布凭据。发布包未进行商业代码签名，首次运行可能出现系统安全提示。
