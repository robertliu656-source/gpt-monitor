GPT Monitor · 自动朗读 Codex 新回复
GPT Monitor · Read new Codex replies aloud
版本：0.2.0
出品：OpenClose
作者：刘天华
邮箱：robert.liu656@gmail.com

【这是给谁用的】
使用 Mac 的视障用户，以及希望通过听觉接收 Codex 新回复的用户。

【这是什么软件】
GPT Monitor 是独立、非官方的本机后台朗读工具。它读取本机 Codex 会话文件中的新助手回复，使用 macOS 语音朗读。它不是 OpenAI 官方产品，也不会自动操作你的任务。

【为什么需要它】
不用反复寻找新消息，回复到达后即可听到内容。暂停开关可随时让程序安静。

【它如何解决问题】
后台监听新回复，过滤工具输出及内部内容，避免重复朗读。它按完整消息开始朗读，并非逐个 token 实时朗读。新任务优先于旧队列；多个任务同时运行时可能切换到更新的回复。

【它能做什么】
默认使用本地婷婷语音，速度 750，音量 70%。
Control＋Command＋M：暂停，再按恢复；暂停期间新回复会被忽略。
Control＋Command＋斜杠和复制快捷键在默认模式中未启用。
需要用户处理时可播报“需要你处理”。已移除火柴音效。
英文版使用 Samantha 英文语音和英文提示，默认速度 220。程序保留回复原文，不自动翻译。

【使用方法】
1. 将 GPT Monitor.app 放到个人“应用程序”文件夹（~/Applications），再双击打开。
2. 听到“GPT Monitor 开始监听”后，在 Codex 中开始新的对话回复。
3. 使用 Control＋Command＋M 暂停或恢复。
4. 首次启动会安装用户级登录启动项。默认 M 键不需要输入监控权限。
5. 如系统阻止打开，按 macOS“隐私与安全性”提供的确认方式操作；不要关闭系统安全保护。

【系统要求】
Apple Silicon Mac。已在 macOS 26.6 系列验证；Intel 和其他 macOS 版本未验证。
打包版含 Python 运行时，不需另装 Python。使用本机会话文件；不保证支持未写入这些文件的云端或网页对话。
当前应用是本地 ad-hoc 签名，未经过 Developer ID 签名或 Apple 公证。

【API Key 配置（首次使用）】
默认本地朗读不需要 API Key，也不需要联网合成语音。
实际配置位置：~/Library/Application Support/OpenClose/GPT Monitor/config.txt
项目或发布包的 config.txt 只用于首次安装初始化，已有配置不会被覆盖。
英文切换：把项目 config.en.txt 的内容作为运行配置，重启应用。恢复中文时使用项目 config.txt。
两种版本共用一个运行配置和登录启动项，不同时安装运行两个版本。

【关于模型自动切换】
本工具没有问答模型。默认 low_latency=true，仅使用本地语音。
可选在线模式 low_latency=false 使用微软云端语音，发送朗读文字并在本机缓存临时音频；失败后回退本地。中文使用云希，英文使用 Aria。在线服务依赖第三方接口，可能不可用。

【常见问题】
没有声音：先按 M 组合键检查暂停状态，并核对系统输出设备。仍无声时可重启后台服务。
停止和取消登录启动、重启以及详细检查命令见 GitHub README 的维护部分。
旧消息通常不会在启动时补读；本工具不保证保留暂停期间的新消息。
语速、音量和 local_voice 在运行配置中调整，重启后生效。英文和中文速度数字不能视为相同听感。
日志：~/Library/Logs/OpenClose/GPT Monitor/gpt_monitor.log
缓存：~/Library/Caches/OpenClose/GPT Monitor/
状态：~/Library/Application Support/OpenClose/GPT Monitor/state/
默认本地模式不持久保存完整回复；日志包含事件、会话文件名、计数和状态。可选在线模式会产生音频缓存。应用会读取 ~/.codex/sessions 下的本机会话。

【关于作者】
刘天华，OpenClose。为真实使用者制作简单、实用、无障碍优先的工具。

【反馈与联系】
robert.liu656@gmail.com
反馈请提供应用版本、macOS 版本和问题发生方式；不要提交私人聊天、密钥或完整个人日志。

【版权声明】
项目代码采用 MIT 许可证，详见 LICENSE。第三方依赖保留各自许可证。
macOS 语音和系统音效由系统提供，不随本项目分发。
