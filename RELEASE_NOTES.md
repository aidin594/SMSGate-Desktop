# SMSGate Desk Community — v1.0.0-beta.1

First public **beta** release of the open-source Windows desktop client for Android SMSGate.

## Features
- Browse and search SMS conversations from your own SMSGate Android server.
- Send SMS via SIM1 or SIM2, with confirmation before sending.
- Incoming message notifications (previews off by default).
- Light/dark/system appearance, tray integration and optional Windows startup.
- Local SMS cache and export options.
- Windows Credential Manager integration for optional password storage.
- International phone-number grouping with a configurable dialing country code.

## Download and installation
1. Download **SMSGateDeskCommunity_Windows_v1.0.0-beta.1.zip** from **Assets** below.
2. Extract **the whole ZIP** into a folder of your choice.
3. Run **SMSGateDeskCommunity.exe** inside the extracted **SMSGateDeskCommunity** folder, keeping its **_internal** folder alongside the EXE.
4. Open **Settings** and enter **your own** SMSGate server URL and credentials.

There is no installer or code-signing certificate in this beta. Windows SmartScreen or antivirus software may warn about an unknown publisher.

## Compatibility and privacy
- Windows 10/11; an Android SMSGate installation reachable on a trusted private network.
- Only local/private network gateways are supported; no cloud relay.
- Ordinary HTTP does **not** encrypt your password or SMS traffic. Use a trusted LAN, or a compatible HTTPS setup when available.
- Messages and exported CSV files are stored locally **without encryption**; protect your Windows account.
- This beta does **not** contain your gateway, address, phone numbers, messages or passwords.
- The community edition has its own Windows settings and credential namespace; it does not import settings from the maintainer's private v4.6 app.

## Verification and license
- Automated unit tests, offscreen Qt GUI smoke test, Windows EXE compilation and an isolated Windows Credential Manager round-trip test have passed in GitHub Actions.
- Initial manual feedback confirmed that the Windows window opens and the app can read conversations from a real gateway; outbound SMS interoperability and other environments still need verification.
- **Beta software:** use with care; review [SECURITY.md](SECURITY.md), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), and [DISTRIBUTION_CHECKLIST.md](DISTRIBUTION_CHECKLIST.md). This is not certified for production or sensitive messages.
- Project source: MIT license. Qt/PySide6 binaries have their own LGPL/GPL licensing obligations; applicable notices and license texts are bundled.

Created by **Aidin Shadnezhad**. Not affiliated with the Android SMSGate project.
