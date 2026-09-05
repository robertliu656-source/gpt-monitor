# GPT Monitor / Codex Monitor

Use the global OpenClose Mac standard at `~/.codex/skills/openclose-mac-standard/SKILL.md` when available. Portable project requirements are in `docs/OPENCLOSE_MAC_STANDARD.md`.

This project monitors local Codex session JSONL for assistant responses. Keep control-command-M as the enabled pause/resume shortcut and preserve local Tingting speech at 750 and volume 0.7 unless the user requests otherwise.

Runtime config: `~/Library/Application Support/OpenClose/GPT Monitor/config.txt`.
Installed app: `~/Applications/GPT Monitor.app`.
First diagnose using the app's `--status` and actual say process, then the app log. Do not assume the source config is the live config. Never commit runtime session data, logs or secrets.
