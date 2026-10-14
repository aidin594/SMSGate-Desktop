"""Current-user Windows logon startup for SMSGate Desk.

Only the application's HKCU Run value is touched. No administrator rights,
scheduled tasks, shell scripts, passwords or third-party services are needed.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE_NAME = 'SMSGateDeskCommunity'
BACKGROUND_FLAG = '--background'


class StartupError(RuntimeError):
    """Startup registration failed; explain the error to the user."""


def _winreg():
    if sys.platform != 'win32':
        raise StartupError('Windows startup is available on Windows only.')
    import winreg
    return winreg


def startup_command(executable: str | None = None, frozen: bool | None = None) -> str:
    """Quoted and stable command for the packaged executable, never a temp path."""
    if frozen is None:
        frozen = bool(getattr(sys, 'frozen', False))
    if not frozen:
        raise StartupError('Start with Windows requires the built SMSGateDeskCommunity.exe. Run the EXE to enable it.')
    path = Path(executable or sys.executable).resolve()
    if path.suffix.lower() != '.exe' or not path.is_file():
        raise StartupError('The SMSGateDeskCommunity.exe path is missing. Rebuild and launch the EXE first.')
    return subprocess.list2cmdline([str(path), BACKGROUND_FLAG])


def registered_command() -> str | None:
    """Return the one HKCU Run value owned by this application, if present."""
    reg = _winreg()
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_READ) as key:
            command, kind = reg.QueryValueEx(key, VALUE_NAME)
        if kind != reg.REG_SZ or not isinstance(command, str):
            raise StartupError('Existing Windows startup entry has an unsupported value type.')
        return command
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise StartupError(f'Unable to read Windows startup settings: {exc}') from exc


def set_startup(enabled: bool, command: str | None = None) -> None:
    """Enable or disable only our own Run entry, with readback verification."""
    reg = _winreg()
    if enabled:
        command = command or startup_command()
        try:
            with reg.CreateKeyEx(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
                reg.SetValueEx(key, VALUE_NAME, 0, reg.REG_SZ, command)
        except OSError as exc:
            raise StartupError(f'Unable to enable Start with Windows: {exc}') from exc
        if registered_command() != command:
            raise StartupError('Windows did not retain the startup entry. Check Windows permissions.')
    else:
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
                try:
                    reg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise StartupError(f'Unable to disable Start with Windows: {exc}') from exc
        if registered_command() is not None:
            raise StartupError('Windows did not remove the startup entry.')


def restore_startup(command: str | None) -> None:
    """Rollback startup registration when saving JSON preferences failed."""
    set_startup(command is not None, command=command)


def registration_hint(command: str | None, *, frozen: bool | None = None,
                      executable: str | None = None) -> str:
    if command is None:
        return 'Off. Enable this option and Save settings to start with Windows.'
    try:
        expected = startup_command(executable=executable, frozen=frozen)
    except StartupError:
        return 'Registered in Windows. Open the packaged EXE to check or update its startup path.'
    if command.casefold() == expected.casefold():
        return 'Enabled for this EXE. It will launch quietly after you sign in to Windows.'
    return 'Windows points to a different copy of the EXE. Click Save settings to repair the startup path.'
