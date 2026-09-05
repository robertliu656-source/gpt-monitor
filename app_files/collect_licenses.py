"""Collect installed distribution license files for a binary release."""
from importlib.metadata import distributions
from pathlib import Path
import shutil
import sys


def collect(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    index = ["Third-party distributions in the build environment", "",
             "Some build-only packages may not be included in the application.", ""]
    for dist in sorted(distributions(), key=lambda d: d.metadata.get("Name", "")):
        name = dist.metadata.get("Name", "unknown")
        index.append(f"{name} {dist.version}")
        index.extend(dist.metadata.get_all("Project-URL") or [])
        if dist.metadata.get("Home-page"):
            index.append(dist.metadata["Home-page"])
        for entry in dist.files or []:
            path = Path(str(entry))
            if any(part == ".." for part in path.parts):
                continue
            if not any(word in path.name.lower() for word in ("license", "copying", "copyright", "notice")):
                continue
            source = Path(dist.locate_file(entry))
            if not source.is_file() or source.suffix in (".py", ".pyc"):
                continue
            target = destination / name / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        index.append("")
    (destination / "INDEX.txt").write_text("\n".join(index), encoding="utf-8")


if __name__ == "__main__":
    collect(Path(sys.argv[1]))
