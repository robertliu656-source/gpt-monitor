GPT Monitor for Windows · Read local Codex replies aloud
Version 0.2.0 · OpenClose · Liu Tianhua
Contact: robert.liu656@gmail.com

WHO IT IS FOR
Blind and low-vision Windows users and anyone who prefers listening to replies.

WHAT IT DOES AND WHY
Reads new assistant messages from local ~/.codex/sessions files using Windows SAPI voices. Filters internal/tool content using the same parser as the Mac edition. No cloud voice service, API key or Python installation is required for the packaged EXE. Reply text is not translated.

GETTING STARTED
Unzip the entire folder into a permanent location and double-click GPTMonitor.exe. Listen for “GPT Monitor is listening,” then generate a new local Codex reply. The application runs without a main window and does not add itself to Windows startup.

SHORTCUTS
Ctrl+Alt+/ pauses/resumes the current speech. New replies while paused are ignored.
Ctrl+Alt+Q exits. Double-click the EXE to start again. Slash uses the OEM_2 physical key (US-layout slash); on other layouts that key may have another label.
The first Windows release reads queued replies in arrival order. Unlike the Mac edition, it does not interrupt current speech to prioritize a new task.

REQUIREMENTS
64-bit Windows 10/11 with a SAPI-compatible installed voice. Build and automated smoke tests run in GitHub's Windows environment; physical speakers, screen readers and shortcuts on users' PCs still require field testing. Windows ARM and 32-bit systems are unverified.
The EXE is not Authenticode-signed. Windows SmartScreen or managed-device rules may warn or block it. Do not disable security software. Verify the download source before allowing a per-app exception.

LANGUAGE AND SETTINGS
English defaults to the first installed English SAPI voice. Chinese needs a compatible Chinese SAPI voice; not every voice visible in Narrator is exposed through SAPI.
Runtime file: %LOCALAPPDATA%\OpenClose\GPT Monitor\config.txt
The package config is copied only on first launch. English and Chinese packages share settings and the application name; run only one copy.
To switch language, exit, copy the selected package's config.txt over the runtime config, and launch again.
language=en-US or zh-CN
voice_name= : leave blank for language selection, or enter a name fragment matching an installed SAPI voice.
rate=0 : Windows SAPI scale -10 to 10, not words per minute.
volume=70 : range 0 to 100.
No chatbot models or model fallback are used. If no matching voice is installed, the app explains the problem and exits.

TROUBLESHOOTING AND PRIVACY
Check pause state, output device and voice installation. Ctrl+Alt+Q exits; reopening restarts listening without replaying all old replies.
status.json and monitor.log are in the runtime folder. Status is a timestamped snapshot, not proof a process is still alive. Logs contain event metadata and session filenames, not full reply text. Speech stays local. Startup is manual.
Only local Codex session files are supported. Web/cloud-only conversations may not exist there. Format changes can affect compatibility.

ABOUT / FEEDBACK / COPYRIGHT
OpenClose makes practical accessibility-focused tools. Send feedback to robert.liu656@gmail.com with version and reproduction steps; omit private chats and secrets.
Independent project, not an official OpenAI product. Project code is MIT; bundled dependencies retain their licenses. Windows voices are not redistributed. The match sound is not included.
