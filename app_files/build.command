#!/bin/zsh
set -euo pipefail

project_dir="${0:A:h:h}"
venv_python="$project_dir/.venv/bin/python"
pyinstaller="$project_dir/.venv/bin/pyinstaller"
build_root="$project_dir/build"
pyinstaller_dist="$build_root/pyinstaller"
pyinstaller_work="$build_root/pyinstaller-work"
version="0.2.0"
edition="${1:-zh}"
[[ "$edition" == "zh" || "$edition" == "en" ]] || { print -u2 'Usage: build.command [zh|en]'; exit 2; }
suffix=""
config_template="$project_dir/config.txt"
readme_template="$project_dir/README.txt"
if [[ "$edition" == "en" ]]; then
  suffix="-en"
  config_template="$project_dir/config.en.txt"
  readme_template="$project_dir/README.en.txt"
fi
staging="$project_dir/dist/GPTMonitor_Mac_$version$suffix.staging"
release="$project_dir/dist/GPTMonitor_Mac_$version$suffix"
icon_png="$build_root/GPTMonitor-1024.png"
iconset="$build_root/GPTMonitor.iconset"
icon_icns="$build_root/GPTMonitor.icns"

test "$(uname -m)" = "arm64"
test -x "$venv_python"

PYTHONPATH="$project_dir/app_files" "$venv_python" -m unittest discover -s "$project_dir/app_files/tests" -q
PYTHONPATH="$project_dir/app_files" "$venv_python" - <<PY
from pathlib import Path
from release import clear_generated
root=Path("$project_dir")
clear_generated(root/"build/pyinstaller", root/"build")
clear_generated(root/"build/pyinstaller-work", root/"build")
clear_generated(Path("$staging"), root/"dist")
PY

mkdir -p "$build_root" "$iconset" "$staging"
/usr/bin/swift "$project_dir/app_files/make_icon.swift" "$icon_png"
for spec in "16 icon_16x16.png" "32 icon_16x16@2x.png" "32 icon_32x32.png" "64 icon_32x32@2x.png" "128 icon_128x128.png" "256 icon_128x128@2x.png" "256 icon_256x256.png" "512 icon_256x256@2x.png" "512 icon_512x512.png" "1024 icon_512x512@2x.png"; do
  pixels="${spec%% *}"
  name="${spec#* }"
  /usr/bin/sips -z "$pixels" "$pixels" "$icon_png" --out "$iconset/$name" >/dev/null
done
/usr/bin/iconutil -c icns "$iconset" -o "$icon_icns"

"$pyinstaller" \
  --noconfirm \
  --windowed \
  --name "GPT Monitor" \
  --osx-bundle-identifier "com.openclose.gptmonitor" \
  --target-architecture arm64 \
  --icon "$icon_icns" \
  --distpath "$pyinstaller_dist" \
  --workpath "$pyinstaller_work" \
  --specpath "$build_root" \
  --add-data "$project_dir/config.txt:." \
  --add-data "$project_dir/app_files/tests:tests" \
  --hidden-import AVFoundation \
  --hidden-import Quartz \
  --hidden-import AppKit \
  --hidden-import Foundation \
  --hidden-import unittest.mock \
  --hidden-import gpt_monitor \
  --hidden-import release \
  "$project_dir/app_files/gpt_monitor.py"

app="$pyinstaller_dist/GPT Monitor.app"
/usr/bin/ditto "$config_template" "$app/Contents/Resources/config.txt"
test -x "$app/Contents/MacOS/GPT Monitor"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $version" "$app/Contents/Info.plist" 2>/dev/null || /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $version" "$app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $version" "$app/Contents/Info.plist" 2>/dev/null || /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $version" "$app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$app/Contents/Info.plist" 2>/dev/null || /usr/libexec/PlistBuddy -c "Set :LSUIElement true" "$app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :NSInputMonitoringUsageDescription string GPT Monitor needs Input Monitoring only to detect its configured global shortcuts." "$app/Contents/Info.plist" 2>/dev/null || true
/usr/bin/codesign --force --deep --sign - --identifier com.openclose.gptmonitor "$app"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$app"

/usr/bin/ditto "$app" "$staging/GPT Monitor.app"
/usr/bin/ditto "$config_template" "$staging/config.txt"
/usr/bin/ditto "$readme_template" "$staging/README.txt"
if [[ "$edition" == "zh" ]]; then
  /usr/bin/ditto "$project_dir/使用说明.txt" "$staging/使用说明.txt"
fi
/usr/bin/ditto "$project_dir/LICENSE" "$staging/LICENSE"
/usr/bin/ditto "$project_dir/THIRD_PARTY_NOTICES.md" "$staging/THIRD_PARTY_NOTICES.md"
"$venv_python" "$project_dir/app_files/collect_licenses.py" "$staging/Third-Party-Licenses"

test -x "$staging/GPT Monitor.app/Contents/MacOS/GPT Monitor"
/usr/bin/plutil -lint "$staging/GPT Monitor.app/Contents/Info.plist"
/usr/bin/codesign --verify --deep --strict "$staging/GPT Monitor.app"
"$staging/GPT Monitor.app/Contents/MacOS/GPT Monitor" --selftest

PYTHONPATH="$project_dir/app_files" "$venv_python" - <<PY
from pathlib import Path
from release import atomic_promote
atomic_promote(Path("$staging"), Path("$release"))
PY

printf '%s\n' "$release"
