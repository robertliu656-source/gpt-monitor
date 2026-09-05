from __future__ import annotations

from pathlib import Path
import os
import plistlib
import subprocess


LABEL = "com.openclose.gptmonitor"


def launch_agent_payload(executable: str) -> dict:
    return {
        "Label": LABEL,
        "ProgramArguments": [executable, "--daemon", "--no-greeting"],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Interactive",
        "ThrottleInterval": 5,
    }


def write_launch_agent(path: Path, executable: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = plistlib.dumps(launch_agent_payload(executable), fmt=plistlib.FMT_XML, sort_keys=True)
    temp = path.with_suffix(".plist.tmp")
    temp.write_bytes(payload)
    os.replace(temp, path)


def domain() -> str:
    return f"gui/{os.getuid()}"


def loaded() -> bool:
    result = subprocess.run(
        ["/bin/launchctl", "print", f"{domain()}/{LABEL}"],
        capture_output=True,
        check=False,
        timeout=10,
    )
    return result.returncode == 0


def bootstrap(path: Path) -> None:
    if loaded():
        subprocess.run(["/bin/launchctl", "kickstart", "-k", f"{domain()}/{LABEL}"], check=False, timeout=15)
    else:
        subprocess.run(["/bin/launchctl", "bootstrap", domain(), str(path)], check=True, timeout=15)


def bootout(path: Path) -> None:
    if loaded():
        subprocess.run(["/bin/launchctl", "bootout", domain(), str(path)], check=False, timeout=15)
