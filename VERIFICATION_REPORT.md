# Verification report — 1.0.0-beta.1 (source preview)

Verification environment: Linux, Python 3.13, 2026-10-14.

## Automated checks

- Python module compilation: **PASS** (`python -m compileall -q .`).
- Domain/storage/logic/static automated tests: **68 discovered, 67 passed, 1 skipped**.
- Skipped test: native Windows Credential Manager integration (requires Windows).
- User accounts, Windows startup registry and gateway API are mocked in test fixtures.
- No real SMS sent by tests.

## Not yet validated

- Windows 10/11 GUI smoke execution with installed PySide6.
- Windows PyInstaller `--onedir` build and standalone EXE launch.
- Windows credential self-test from frozen EXE.
- Actual LAN gateway connection and both physical SIM cards.
- Third-party binary license audit for an actual built distribution.

CI workflow at `.github/workflows/windows.yml` is configured to run these Windows steps **after the source is placed in a GitHub repository**; a configured workflow is not the same as a passing workflow.

## Separation and privacy checks

- Private `SMSGateDesk` data directory is **not used** by Community.
- Private `SMSGateDesk` WinCred namespace is **not used** by Community.
- Private `SMSGateDesk` Windows autostart registry value is **not used** by Community.
- No personal preconfigured URL or username in `DEFAULT_SETTINGS`.
- The `192.168.1.10` sample is an illustrative LAN address only.
- No secret/password/message database is bundled in this source archive.

This is not a verified, ready-to-install Windows binary.
