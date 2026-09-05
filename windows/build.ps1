param([ValidateSet('en','zh')][string]$Language = 'en')
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $ProjectRoot
$env:PYTHONPATH = "$ProjectRoot\app_files;$ProjectRoot\windows"
python -m unittest discover -s windows -p 'test_*.py' -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
python -m PyInstaller --noconfirm --clean --onefile --windowed --name GPTMonitor --paths app_files --hidden-import win32com.client --hidden-import pythoncom --hidden-import pywintypes --distpath build/windows-bin --workpath build/windows-work --specpath build windows/gpt_monitor_windows.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
$Package = "dist/GPTMonitor_Windows_0.2.0-$Language"
New-Item -ItemType Directory -Force $Package | Out-Null
Copy-Item build/windows-bin/GPTMonitor.exe $Package
if ($Language -eq 'zh') {
    Copy-Item windows/config.zh.txt "$Package/config.txt"
    Copy-Item windows/README.zh.txt "$Package/README.txt"
} else {
    Copy-Item windows/config.txt "$Package/config.txt"
    Copy-Item windows/README.en.txt "$Package/README.txt"
}
Copy-Item LICENSE,THIRD_PARTY_NOTICES.md $Package
python app_files/collect_licenses.py "$Package/Third-Party-Licenses"
if ($LASTEXITCODE -ne 0) { throw 'License collection failed' }
$Label = if ($Language -eq 'zh') { 'Chinese' } else { 'English' }
Compress-Archive -Path $Package -DestinationPath "dist/GPT-Monitor-0.2.0-Windows-$Label-x64.zip" -Force
