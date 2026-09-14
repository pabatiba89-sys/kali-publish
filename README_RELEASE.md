# Kali Publish 可执行版

这个压缩包内含 Kali Publish 后端及 Python/Playwright 运行环境，不需要安装 Python。运行前需要安装 Google Chrome。

## macOS（Apple Silicon）

1. 解压 `kali-publish-*-macos-arm64.zip`。
2. 在终端进入解压后的 `kali-publish` 目录。
3. 运行 `./kali-publish`。

本版本未进行 Apple Developer 签名。如果 macOS 阻止首次运行，请先核对 Release 页的 SHA-256 文件，再运行：

```bash
xattr -dr com.apple.quarantine kali-publish
./kali-publish
```

## Windows（x64）

1. 解压 `kali-publish-*-windows-x64.zip`。
2. 双击 `kali-publish.exe`，或在命令提示符中运行它。

本版本未进行代码签名，Windows SmartScreen 可能提示未知发布者。

## 使用与数据位置

启动成功后，健康检查地址是 <http://127.0.0.1:5409/health>。按 `Ctrl+C` 停止服务。

- macOS 数据：`~/Library/Application Support/Kali Publish/`
- Windows 数据：`%LOCALAPPDATA%\Kali Publish\`

可通过环境变量 `KALI_PUBLISH_DATA_DIR` 更改数据目录，通过 `LOCAL_CHROME_PATH` 指定 Chrome 路径。服务没有公网用户认证，只应监听本机地址。
