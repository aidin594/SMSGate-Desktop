# Changelog

## 1.0.0-beta.1 — Source preview (2026-10-14)

- Community edition forked from privately maintained SMSGate Desk 4.6, with separate settings/cache, credentials and Windows autostart registry name.
- Removed personal network address and username defaults.
- Added an optional dialing country code instead of assuming Sweden for all users; conservative international formatting remains recommended.
- Added MIT license, project documentation, contributor/security guidelines, CI and licensing notices.
- Kept the original conversation UI and send confirmation flow.

**Verification:** source syntax and Python unit tests passed on Linux. Windows GUI smoke, native credentials and packaged executable require validation on Windows before a stable release.
