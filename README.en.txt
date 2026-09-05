GPT Monitor · Read new Codex replies aloud
Version: 0.2.0
By OpenClose
Author: Liu Tianhua
Email: robert.liu656@gmail.com

WHO THIS IS FOR
Mac users who are blind or have low vision, and anyone who prefers listening to new Codex replies.

WHAT IT IS
GPT Monitor is an independent, unofficial background reader for local Codex session files. It speaks new assistant replies using macOS text-to-speech. It is not an OpenAI product and does not operate your tasks.

WHY USE IT
Hear incoming replies without repeatedly searching the screen. Pause and resume with one keyboard shortcut.

HOW IT WORKS
The listener reads complete new assistant messages, filters internal content and tool output, and avoids duplicate speech. It does not provide token-by-token streaming. New tasks take priority; simultaneous tasks can interrupt older queued replies.

WHAT IT CAN DO
The English edition uses the built-in Samantha English voice at a default rate of 220 and 70% volume.
Press Control+Command+M to pause; press it again to resume. New replies received while muted are ignored.
Control+Command+/ and the copy shortcut are disabled in the default configuration.
All application speech prompts are available in English. The match sound has been removed.
Replies remain in their original language; this app does not translate them. Choose an installed voice appropriate for the reply language.
A Chinese edition uses Tingting at a rate of 750. Both editions have the same application name: GPT Monitor.

GETTING STARTED
1. Place GPT Monitor.app in your personal Applications folder (~/Applications).
2. Double-click it. You should hear “GPT Monitor is listening.”
3. Generate a new reply in the local Codex app.
4. Use Control+Command+M to pause or resume.
First launch installs a per-user login agent. The default shortcut does not need Input Monitoring permission.
If macOS blocks the app, use the confirmation offered in Privacy & Security. Do not disable system security protections.

SYSTEM REQUIREMENTS
Apple Silicon Mac. Validated on macOS 26.6-series systems; Intel Macs and other macOS releases have not been validated.
The packaged app includes its Python runtime. End users do not need to install Python.
Only conversations written to local Codex session files are supported; web and cloud-only conversations may not be available.
The app currently uses an ad-hoc signature. It is not Developer ID signed or notarized by Apple.

API KEY AND CONFIGURATION
No API key is required. Default local speech synthesis works offline.
Runtime configuration: ~/Library/Application Support/OpenClose/GPT Monitor/config.txt
The bundled config initializes a new installation only. Existing preferences are preserved.
To switch an existing installation to English, replace the runtime config contents with config.en.txt from the source project and restart. Use the project's config.txt to return to Chinese.
The two editions share one configuration and one login agent. Run only one installed copy.
You may choose another voice installed on your Mac using local_voice. Rates have different perceived speeds across languages.

ENGINE FALLBACK
There is no chatbot model in this app. With low_latency=true, speech is synthesized locally.
The optional low_latency=false mode sends reply text to Microsoft's online speech service and creates temporary local audio files. English uses Aria; Chinese uses Yunxi. Failures fall back to the local voice. The third-party service can change or become unavailable.

TROUBLESHOOTING
If silent, check the mute shortcut and your Mac's output device. Restart the service if needed.
The GitHub README maintenance section documents restart, status and stopping the login agent.
Existing messages are generally not replayed at startup. Replies received while muted are not retained for replay.
Configuration changes take effect after restart.
Logs: ~/Library/Logs/OpenClose/GPT Monitor/gpt_monitor.log
Cache: ~/Library/Caches/OpenClose/GPT Monitor/
State: ~/Library/Application Support/OpenClose/GPT Monitor/state/

PRIVACY
The app reads local files under ~/.codex/sessions. Default local mode does not persist full reply text. Logs can include session filenames, event types, counts and status. Optional online mode sends text to the speech provider and creates audio cache files. Do not share personal session files or unredacted logs in issues.

ABOUT THE AUTHOR
Liu Tianhua builds practical, accessibility-focused OpenClose tools for everyday users.

FEEDBACK
robert.liu656@gmail.com
Include the app version, macOS version and steps to reproduce. Never include private conversations, API keys or credentials.

COPYRIGHT
Project code is licensed under MIT; see LICENSE. Third-party components retain their own licenses.
Apple voices and system sounds are supplied by macOS and are not redistributed.
