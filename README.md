# Kali Publish

从 `social-auto-upload-baijiahao` 中独立出来的本地多平台视频发布后端。它只包含账号登录、登录态校验、本地视频管理和发布 API，不包含原项目的 Notion、数字人、素材库、支付、用户及积分业务。

## 支持范围

| Type | 平台 | API 扫码登录 | 发布 |
|---:|---|:---:|:---:|
| 1 | 小红书 | 是 | 是 |
| 2 | 视频号 | 是 | 是 |
| 3 | 抖音 | 是 | 是 |
| 4 | 快手 | 是 | 是 |
| 5 | TikTok | 否 | 是 |
| 6 | YouTube | 否 | 是 |

TikTok 和 YouTube 保留原有发布适配器，但原 HTTP 后端没有对应的扫码登录入口，需要预先准备兼容的 Playwright 登录态文件。

## 安装与启动

要求 Python 3.10 或更高版本，以及本机可用的 Chrome/Chromium。当前项目已在 Python 3.14 完成导入和测试。首次安装：

```bash
chmod +x install.sh start.sh
./install.sh
./start.sh
```

服务默认只监听 `127.0.0.1:5409`。如需指定本机 Chrome，复制 `.env.example` 中的变量到自己的运行环境；项目不会自动读取或提交 `.env`。

## 下载可执行版

GitHub Releases 同时提供 Apple Silicon（macOS arm64）和 Windows x64 压缩包。可执行版不需要安装 Python，但必须先安装 Google Chrome。下载后请先使用同名 `.sha256` 文件校验完整性，具体启动方式见压缩包中的 `README.md`。

发布包由 GitHub Actions 在对应系统上分别构建，并在两个平台的测试和浏览器冒烟检查全部通过后发布。当前版本未进行 Apple Developer 或 Windows 商业代码签名，首次运行可能出现系统安全提示。

## 主要 API

- `GET /health`：健康检查
- `GET /api/platforms`：平台能力列表
- `POST /upload`、`GET /getFiles`、`GET /getFile`、`DELETE /deleteFile`：视频文件管理
- `GET /getAccounts`、`GET /getValidAccounts`、`GET /login`、`POST /updateUserinfo`、`DELETE /deleteAccount`：发布账号管理
- `POST /postVideo` 或 `POST /api/publish`：单次发布
- `POST /postVideoBatch` 或 `POST /api/publish/batch`：批量发布

原接口名保留，便于现有前端切换仓库后继续使用。

## 安全边界

这是本机自动化服务，不带用户认证，不应直接暴露到公网。`cookiesFile/` 保存平台登录态，`videoFile/` 保存待发布视频，二者都已加入 `.gitignore`。仓库不包含七牛、Notion 或其他真实密钥。

平台页面结构变化时，浏览器自动化选择器可能需要更新。请遵守各平台条款，只操作你有权管理的账号和内容。

## 来源与许可证

浏览器自动化适配器基于 [dreammis/social-auto-upload](https://github.com/dreammis/social-auto-upload) 的 MIT 许可代码，并保留其原始版权声明。本项目新增的独立 Flask API、配置隔离和测试同样采用 MIT License，详见 `LICENSE`。
