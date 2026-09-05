# GPT Monitor

Read new local Codex replies aloud on macOS. An independent, unofficial OpenClose accessibility tool.

**Version 0.2.0 · Apple Silicon · English and 简体中文**

- [English user guide](README.en.txt)
- [中文使用说明](README.txt)
- [OpenClose Mac standard](docs/OPENCLOSE_MAC_STANDARD.md)
- [Data sources and privacy](DATA_SOURCES.md)

GPT Monitor runs in the background and uses macOS speech synthesis. Press **Control+Command+M** to pause or resume. Muted replies are ignored. The old slash and copy shortcuts are disabled by default.

The English edition uses **Samantha, rate 220** and English application prompts. The Chinese edition uses **Tingting, rate 750**. Both use 70% volume. Reply text is preserved without translation. Both editions share the app name and runtime preferences; install one edition at a time.

## Install

**[Download the Mac apps / 下载 Mac 应用](https://github.com/robertliu656-source/gpt-monitor/releases/latest)**

Choose the **English** or **Chinese** ZIP for Apple Silicon, unzip it, then move GPT Monitor.app into your Applications folder. Install one language edition at a time. The first release is unsigned by Developer ID and not notarized; see the release notes for first-open instructions.

Build a package using the steps below, then place GPT Monitor.app in ~/Applications and double-click it. The packaged app includes Python. First launch configures a per-user login agent; the default shortcut needs no Input Monitoring permission.

Packages are ad-hoc signed, not Developer ID signed or notarized. Follow macOS's per-app confirmation if needed; do not disable Gatekeeper. Validated on Apple Silicon with macOS 26.6-series systems. Intel and other macOS versions are unverified.

## Configuration

Runtime config: ~/Library/Application Support/OpenClose/GPT Monitor/config.txt.
Bundled templates apply only on first launch. Existing preferences are preserved. Use config.en.txt for English or config.txt for Chinese, then restart. To change voice, use a name listed by `say -v '?'`; choose a voice matching the language of the replies.

Default speech is local and requires no API key. Optional online mode (`low_latency=false`) sends text to Microsoft's speech service and temporarily caches audio. It falls back to local speech on error. The legacy `translate_english` setting does not implement translation.

## Maintenance

With the app installed in your personal Applications folder:

```sh
"$HOME/Applications/GPT Monitor.app/Contents/MacOS/GPT Monitor" --status
"$HOME/Applications/GPT Monitor.app/Contents/MacOS/GPT Monitor" --restart
"$HOME/Applications/GPT Monitor.app/Contents/MacOS/GPT Monitor" --stop
```

`--stop` unloads the login agent. Double-click to start again. State reports controller/listener health, mute state and speech settings; verify actual speech too if the app is silent.

## Build and test

For developers: use Apple Silicon macOS, Xcode Command Line Tools and Python 3.14 (the tested runtime).

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r app_files/requirements.txt
PYTHONPATH=app_files .venv/bin/python -m unittest discover -s app_files/tests -q
zsh app_files/build.command zh
zsh app_files/build.command en
```

Outputs: `dist/GPTMonitor_Mac_0.2.0/` and `dist/GPTMonitor_Mac_0.2.0-en/`.
Build sequentially because the two editions share intermediate build directories. Source and build artifacts are kept separate. Do not commit runtime data, credentials, logs or generated binaries.

## Limitations

This tool reads local Codex session JSONL, not the screen. Cloud-only or browser conversations may not appear there. It reads complete messages, not token deltas. Concurrent tasks can supersede older speech. Session formats may change; the app is not affiliated with OpenAI.

## Contact and license

OpenClose · Liu Tianhua · robert.liu656@gmail.com

MIT for project code. See [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY_NOTICES.md). Do not include private conversations or credentials in reports.
