# GPT Monitor 0.2.0 — Mac & Windows · English & Chinese

Download, unzip, and move **GPT Monitor.app** into your personal Applications folder (~/Applications), then double-click it. No Python installation is needed.

- **GPT-Monitor-0.2.0-Mac-English-arm64.zip**: Samantha English voice, English prompts and instructions, default rate 220.
- **GPT-Monitor-0.2.0-Mac-Chinese-arm64.zip**: Tingting Chinese voice, Chinese prompts and instructions, default rate 750.
- **GPT-Monitor-0.2.0-Windows-English-x64.zip**: installed English Windows SAPI voice, English prompts and instructions.
- **GPT-Monitor-0.2.0-Windows-Chinese-x64.zip**: installed Chinese Windows SAPI voice, Chinese prompts and instructions. A compatible Chinese SAPI voice must be installed.
- **SHA256SUMS.txt**: checksums for all four downloads.

## Windows install

Unzip the whole Windows folder to a permanent location and double-click **GPTMonitor.exe**. Python is included. Use **Ctrl+Alt+/** to pause/resume and **Ctrl+Alt+Q** to exit. No login-startup item is added. Windows uses SAPI rate levels (default 0), not Mac's rate numbers. This edition reads replies in queue order and does not yet implement Mac's new-task speech interruption.

Targets x64 Windows 10/11. Windows ARM and 32-bit systems are unverified. EXEs are not Authenticode-signed and may trigger SmartScreen; do not disable security protections. Both languages use %LOCALAPPDATA%\\OpenClose\\GPT Monitor\\config.txt; to change an existing installation's language, exit, replace that file with the chosen package's config.txt, and reopen. Only installed SAPI-compatible voices can be used; not every Narrator voice is exposed to SAPI.

Windows source tests, SAPI speech-file generation, hotkey registration and packaged-EXE smoke checks run in GitHub's Windows environment. **Physical speakers, actual keyboard interaction and screen-reader experience on a user PC have not yet been validated.** The Chinese preset is included, but Chinese SAPI audio was not tested on the hosted runner. This is a new Windows implementation, not the historical 0.5.3 binary.

## Mac install

Requires an **Apple Silicon Mac**. Validated on macOS 26.6-series systems. Intel Macs and other macOS versions are not verified. Uses local Codex session files; not every cloud/web conversation is available.

Press **Control+Command+M** to pause/resume. New replies while muted are ignored. Default speech runs locally and needs no API key. Reply text is not translated. The match sound has been removed.

## First launch

This release is **ad-hoc signed, not Developer ID signed or notarized by Apple**. If macOS blocks the downloaded app, attempt to open it once, then use **System Settings → Privacy & Security → Open Anyway**, if offered. Confirm opening only after verifying the download came from this repository. Do not disable Gatekeeper. Managed Macs may prohibit this exception.

Both editions share the same app name, preferences and login agent. Install only one edition. Existing settings are preserved; downloading the English edition does not overwrite existing Chinese preferences. To switch, copy the selected package's config.txt contents to ~/Library/Application Support/OpenClose/GPT Monitor/config.txt and restart the app.

## 中文安装说明

选择文件名包含 **Chinese** 的 ZIP，下载解压后，将 GPT Monitor.app 放进个人“应用程序”文件夹并双击。不需要安装 Python。

Windows 用户选择文件名包含 **Windows-Chinese-x64** 的 ZIP，完整解压后双击 GPTMonitor.exe。暂停／恢复用 Ctrl＋Alt＋斜杠，退出用 Ctrl＋Alt＋Q。需要安装兼容的中文 SAPI 语音。Windows 安装包未经数字签名，可能出现 SmartScreen 提示；请勿关闭安全保护。Windows 已进行云端构建与英文语音生成、快捷键注册和 EXE 启动测试，真实中文发声、扬声器、键盘操作及屏幕阅读器仍需实机验证。

仅已验证 Apple Silicon Mac、macOS 26.6 系列。英文版选择 **English**。两个版本共用配置，选择一个安装即可。

暂停／恢复：**Control＋Command＋M**。暂停期间新回复不会补读。默认本地朗读，不需要 API Key。已移除火柴音效。

应用未经 Apple 公证。如果首次打开被阻止，尝试打开后，在“系统设置 → 隐私与安全性”使用系统提供的“仍要打开”确认；不要关闭系统安全保护。已有安装会保留配置，切换语言请按包内 README 的说明操作。

## Validation and licensing

Both Mac packaged editions passed 47 tests. English local speech was tested with Samantha; the installed Chinese edition was verified with Tingting at rate 750. Windows has three portable unit tests plus the hosted Windows smoke checks described above. Packages contain MIT project licensing and third-party license files. Apple and Windows voices are supplied by their operating systems, not redistributed.

This is an independent OpenClose project, not an official OpenAI product.
