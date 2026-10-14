# Contributing

Issues, tests, fixes and translations are welcome. Keep the project usable on Windows 10/11 and retain strict SIM selection and send confirmation.

1. Before contributing, check for a related issue; describe the expected behavior and reproduction steps.
2. Make changes on a separate branch and run `python -m unittest discover -s tests -p 'test_*.py' -v`.
3. On Windows, also run `python tests/gui_smoke.py`. Please do not test new sending behavior on other people's phones or SMS accounts.
4. Open a pull request with the purpose, tests, and screenshots if you changed UI.
5. Never submit `settings.json`, `messages.json`, passwords, customer phone numbers, logs, local auth material or real SMS excerpts.

Code contributed under the repository's MIT license unless otherwise agreed. Respect the independent licenses of PySide6/Qt and other libraries.
