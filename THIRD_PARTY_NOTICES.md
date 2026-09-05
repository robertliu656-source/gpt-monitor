# Third-party components

The MIT license covers GPT Monitor's own code, not its dependencies.

- PyObjC (Cocoa, Quartz, AVFoundation): MIT.
- psutil: BSD 3-Clause.
- pywin32 (Windows build): PSF license; see the distribution's license text.
- edge-tts: LGPL v3; optional online synthesis uses Microsoft's service. This is not an official Microsoft SDK and service availability is not guaranteed.
- PyInstaller: GPL v2 or later with its bootloader/distribution exception.
- Other transitive dependencies retain their package licenses.

See app_files/requirements.txt for pinned direct dependencies and each distribution's license files. Retain applicable notices when distributing binaries; this file does not replace their license texts.
Apple speech voices and system audio are invoked from macOS, not bundled. The former match sound is excluded.
