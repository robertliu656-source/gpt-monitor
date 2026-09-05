# GPT Monitor 0.2.0 — Mac English & Chinese

Download, unzip, and move **GPT Monitor.app** into your personal Applications folder (~/Applications), then double-click it. No Python installation is needed.

- **GPT-Monitor-0.2.0-Mac-English-arm64.zip**: Samantha English voice, English prompts and instructions, default rate 220.
- **GPT-Monitor-0.2.0-Mac-Chinese-arm64.zip**: Tingting Chinese voice, Chinese prompts and instructions, default rate 750.
- **SHA256SUMS.txt**: checksums for the two downloads.

Requires an **Apple Silicon Mac**. Validated on macOS 26.6-series systems. Intel Macs and other macOS versions are not verified. Uses local Codex session files; not every cloud/web conversation is available.

Press **Control+Command+M** to pause/resume. New replies while muted are ignored. Default speech runs locally and needs no API key. Reply text is not translated. The match sound has been removed.

## First launch

This release is **ad-hoc signed, not Developer ID signed or notarized by Apple**. If macOS blocks the downloaded app, attempt to open it once, then use **System Settings → Privacy & Security → Open Anyway**, if offered. Confirm opening only after verifying the download came from this repository. Do not disable Gatekeeper. Managed Macs may prohibit this exception.

Both editions share the same app name, preferences and login agent. Install only one edition. Existing settings are preserved; downloading the English edition does not overwrite existing Chinese preferences. To switch, copy the selected package's config.txt contents to ~/Library/Application Support/OpenClose/GPT Monitor/config.txt and restart the app.

## 中文安装说明

选择文件名包含 **Chinese** 的 ZIP，下载解压后，将 GPT Monitor.app 放进个人“应用程序”文件夹并双击。不需要安装 Python。

仅已验证 Apple Silicon Mac、macOS 26.6 系列。英文版选择 **English**。两个版本共用配置，选择一个安装即可。

暂停／恢复：**Control＋Command＋M**。暂停期间新回复不会补读。默认本地朗读，不需要 API Key。已移除火柴音效。

应用未经 Apple 公证。如果首次打开被阻止，尝试打开后，在“系统设置 → 隐私与安全性”使用系统提供的“仍要打开”确认；不要关闭系统安全保护。已有安装会保留配置，切换语言请按包内 README 的说明操作。

## Validation and licensing

Both packaged editions passed 47 tests. English local speech was tested with Samantha; the installed Chinese edition was verified with Tingting at rate 750. Packages contain MIT project licensing and third-party license files. Apple voices are provided by macOS, not redistributed.

This is an independent OpenClose project, not an official OpenAI product.
