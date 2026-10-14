<div align="center">
  <img src="assets/SMSGateDesk.png" alt="SMSGate Desk Community logo" width="116" />
</div>

# SMSGate Desk Community

**Manage SMS from your Android gateway on your Windows PC.**

[**Download Windows beta v1.0.0-beta.1 (ZIP)**](https://github.com/aidin594/SMSGate-Desktop/releases/tag/v1.0.0-beta.1) · [Browse source](https://github.com/aidin594/SMSGate-Desktop) · [Report a bug](https://github.com/aidin594/SMSGate-Desktop/issues/new/choose)



**A community-maintained, open-source Windows desktop client for an Android SMSGate server.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Windows CI](https://github.com/aidin594/SMSGate-Desktop/actions/workflows/windows.yml/badge.svg)](https://github.com/aidin594/SMSGate-Desktop/actions/workflows/windows.yml)

> **Status: public beta (`1.0.0-beta.1`).** Windows CI runs 68 unit tests, an offscreen GUI smoke test, a packaged EXE build, and a disposable Windows Credential Manager round-trip test from the EXE. These automated checks passed on GitHub-hosted Windows. Full end-to-end testing with real Android gateways, varied Windows installations and antivirus products is still needed before calling this a stable release.

Original creator: **Aidin Shadnezhad**.

## Download for Windows

**No Python installation required.** Download [**v1.0.0-beta.1**](https://github.com/aidin594/SMSGate-Desktop/releases/tag/v1.0.0-beta.1), extract the `SMSGateDeskCommunity_Windows_v1.0.0-beta.1.zip` archive, then launch `SMSGateDeskCommunity.exe` **inside its extracted folder**. Keep the `_internal` folder next to the EXE. The first release is unsigned and marked **beta**; verify the source and checksum before running it.

## What it can do

- View incoming and outgoing SMS as conversations (SMSGate API).
- Send SMS through **SIM1** or **SIM2**, with an explicit confirmation before each send.
- Search conversations and inspect/export sent-message history.
- Poll for messages, show optional Windows notifications and run in the system tray.
- Optionally start with Windows (current-user sign-in only).
- Store the gateway password through **Windows Credential Manager**, not in the JSON settings file.
- Support a light, dark or system theme.
- Group local and international numbers using an **optional dialing country code**.

**Limitations:** The app shows messages provided by your SMSGate Android server; it is not a general Android SMS-sync client. SMS from other Android messaging apps may not be listed. Outgoing entries without SIM metadata are marked **SIM unknown**. Only local or private IP addresses (or `localhost`) are accepted for connections, and there is no cloud relay.

## Requirements

- Windows 10/11 (64-bit recommended).
- Android device running an **SMSGate server** compatible with `/health`, `/inbox`, `/messages`, and the send endpoint.
- Both devices on an accessible private network.
- Gateway address, username and password obtained **from your own SMSGate installation**.
- For building from source: Python 3.12 or 3.13, and internet access to download Python dependencies.

## Prebuilt Windows beta (GitHub Actions)

1. Open the [latest successful Windows CI run](https://github.com/aidin594/SMSGate-Desktop/actions/workflows/windows.yml).
2. Under **Artifacts**, download **SMSGateDeskCommunity-Windows-beta** (GitHub sign-in may be required). Artifacts are temporary, currently retained for 14 days; this is not a GitHub Release.
3. Extract the ZIP, keep **all files in the extracted folder**, and run **SMSGateDeskCommunity.exe**. This is an unsigned community beta, so Windows may show a security warning; verify the repository and build before running software.

## Quick start: run source on Windows

1. Download/extract this **source ZIP** into its own folder.
2. Install Python 3.12/3.13 if needed.
3. Double-click **`BUILD_WINDOWS.bat`** to install dependencies, run unit/UI tests and compile the Windows program. It stops if tests fail.
4. Start **`dist\SMSGateDeskCommunity\SMSGateDeskCommunity.exe`**. Keep its entire `dist\SMSGateDeskCommunity` folder; copying only the EXE will not work.
5. In **Settings**, enter your own `http://192.168.1.10:8080`-style local gateway address, username, and password. The example IP is a placeholder, **not a preconfigured server**.
6. Optionally enter your *dialing country code*, e.g. `46` (Sweden), `44` (UK), `1` (US/Canada), `98` (Iran). Include a `+` and country code on recipient numbers whenever possible. Select SIM1 or SIM2 and save settings.

**Safer first-use advice:** Leave *Start automatically with Windows* off until you have tested the connection; do not enable *SMS text in notifications* on shared computers.

If you're running from source and do not need a packaged EXE, run `py -3 -m pip install -r requirements.txt`, then `py -3 app.py`. Windows autostart intentionally requires a packaged EXE.

## Developer workflow

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -v
.venv\Scripts\python.exe tests\gui_smoke.py
```

All mock tests are designed to avoid sending any SMS. The Windows GUI smoke test uses mock credentials, registry operations and network sync. The standalone EXE credential self-test creates and deletes one disposable Windows credential item (it does **not** touch a real gateway password).

The GitHub Actions workflow runs a Windows check and creates a **build artifact**, **not** an automatic public Release. Review test outcomes, third-party notices and the ZIP before publishing it.

## Separate from the original private v4.6

Community is intentionally isolated from the private version:

| Resource | Community edition |
|---|---|
| Executable | `SMSGateDeskCommunity.exe` |
| Configuration, local SMS cache & logs | `%LOCALAPPDATA%\SMSGateDeskCommunity` |
| Windows credential target prefix | `SMSGateDeskCommunity:` |
| Windows startup value (HKCU Run) | `SMSGateDeskCommunity` |

The public version does **not** automatically import private settings, passwords, or messages. No real gateway address or login is prefilled.

## Privacy & security

- **HTTP Basic Authentication over plain HTTP is *not encrypted*.** Your gateway password and SMS traffic can be visible to devices on the network. Prefer HTTPS with valid certificates when supported; otherwise use only a trusted private LAN. This app intentionally refuses public IP gateways and HTTP redirects.
- The local message cache (`messages.json`) and optional CSV exports contain **unencrypted private messages** and phone numbers. Keep your Windows account secure and do not commit or share these files.
- Windows notifications can reveal SMS contents if preview is enabled (preview is disabled by default).
- Passwords can be stored in Windows Credential Manager if *Remember password* is selected (off by default).
- The program does not upload analytics, and no SMS is sent without confirmation.
- Development tests use synthetic samples and mocks, not personal customer data.

Please report security issues privately via the procedure in [SECURITY.md](SECURITY.md), not in a public issue.

## Contributing and license

Please read [CONTRIBUTING.md](CONTRIBUTING.md). This project's **own source code** is licensed under the **MIT License**; see [LICENSE](LICENSE). PySide6/Qt and other dependencies retain their separate licenses and obligations. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [DISTRIBUTION_CHECKLIST.md](DISTRIBUTION_CHECKLIST.md).

This independent project is **not affiliated with or endorsed by** the Android SMSGate developers or the Qt Company.
