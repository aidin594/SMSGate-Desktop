# Binary distribution checklist (maintainer)

**Do not automatically declare an EXE release production-ready.** Review this checklist for each release:

- [ ] Windows unit tests and offscreen Qt smoke test pass on a supported Windows machine.
- [ ] Packaged EXE launches, shows icon and settings, uses `SMSGateDeskCommunity` data and credential namespaces.
- [ ] Packaged EXE Windows credential self-test passes and deletes its disposable credential.
- [ ] Optional start-with-Windows behavior is tested **without** changing unrelated Run entries.
- [ ] Manual gateway checks completed on a device owned by a tester (never live SMS during automated CI).
- [ ] No private tokens, gateway credentials, personal message cache, logs or real SMS numbers in published tree/history/artifacts.
- [ ] Ship `LICENSE`, `THIRD_PARTY_NOTICES.md` and `LICENSES` alongside the application.
- [ ] Audit all bundled dependency binary notices, including Qt, shiboken, Python and relevant transitive libraries.
- [ ] With LGPLv3 Qt builds, users must be permitted to debug modifications of LGPL software and replace/relink compatible Qt components. Document location of replaceable Qt DLLs and how to rebuild the app; don't restrict these rights in an EULA. Confirm that PyInstaller onedir packaging permits this on the supported deployment.
- [ ] Provide Qt and PySide6 corresponding source availability information (e.g. the exact upstream source URL, versions and modification notices as applicable).
- [ ] Verify that the release zip contains the *whole* `SMSGateDeskCommunity` folder, not only `.exe`.
- [ ] Mark version as **beta** until the full compatibility checklist has passed.

Useful references: [Qt for Python licensing](https://doc.qt.io/qtforpython-6/commercial/index.html), [GNU LGPLv3](https://www.gnu.org/licenses/lgpl-3.0.html).
