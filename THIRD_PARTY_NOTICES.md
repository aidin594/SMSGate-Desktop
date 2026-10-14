# Third-party software and licenses

SMSGate Desk Community's original application code is MIT licensed. This does **not** relicense its dependencies or remove their redistribution conditions.

- **PySide6 / Qt for Python**, Qt Company and contributors: available under **LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only**, or a separate commercial license. This project uses the LGPLv3 route and builds in `--onedir` mode so shared Qt DLLs remain separate and users can replace compatible Qt libraries. See [Qt license information](https://doc.qt.io/qtforpython-6/commercial/index.html) and [PySide6](https://pypi.org/project/PySide6/).
- **Requests** and dependencies: see installed wheel metadata for each distributed release. Requests is generally Apache-2.0 licensed.
- **PyInstaller** (build-time packaging tool): licensed under GPL terms with a special exception for bundling the bootloader; read its installed license details before redistributing. It is not distributed as a standalone Python package with this source.
- **Python runtime** bundled with packaged executables: the Python Software Foundation license and other relevant notices should accompany release distributions where applicable.

`LICENSES/LGPL-3.0.txt` and `LICENSES/GPL-3.0.txt` are reference copies of those licenses. The project's separate MIT `LICENSE` applies only to its own original code.

**Release maintainers:** Verify the actual versions and exact licenses of every binary/wheel included in the built output, preserve notices, and document how users can replace or modify LGPL components. See [DISTRIBUTION_CHECKLIST.md](DISTRIBUTION_CHECKLIST.md). This source snapshot is *not* a legal guarantee that all future binary distributions automatically comply.
