"""Tests use a simulated HKCU registry: never touch the user's real startup apps."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import startup_utils as su


class FakeKey:
    def __init__(self, registry):
        self.registry = registry

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class FakeRegistry:
    HKEY_CURRENT_USER = object()
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self):
        self.values = {'UnrelatedStartupApp': ('unrelated.exe', self.REG_SZ)}
        self.fail_write = False

    def OpenKey(self, hive, path, _reserved, access):
        assert hive == self.HKEY_CURRENT_USER
        assert path == su.RUN_KEY
        return FakeKey(self)

    def CreateKeyEx(self, hive, path, _reserved, access):
        return self.OpenKey(hive, path, _reserved, access)

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name]

    def SetValueEx(self, key, name, _reserved, data_type, command):
        if self.fail_write:
            raise PermissionError('denied')
        self.values[name] = (command, data_type)

    def DeleteValue(self, key, name):
        if self.fail_write:
            raise PermissionError('denied')
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.registry = FakeRegistry()
        self.patcher = patch.object(su, '_winreg', return_value=self.registry)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_startup_can_be_enabled_and_disabled_safely(self):
        su.set_startup(True, r'"C:\Program Files\SMSGate Desk\SMSGateDesk.exe" --background')
        self.assertIn('--background', su.registered_command())
        su.set_startup(True, r'"C:\Program Files\SMSGate Desk\SMSGateDesk.exe" --background')
        su.set_startup(False)
        self.assertIsNone(su.registered_command())
        su.set_startup(False)
        self.assertIn('UnrelatedStartupApp', self.registry.values)

    def test_rollback_restores_previous_path(self):
        original = r'"C:\Old\SMSGateDesk.exe" --background'
        su.set_startup(True, original)
        su.set_startup(True, r'"C:\New\SMSGateDesk.exe" --background')
        su.restore_startup(original)
        self.assertEqual(su.registered_command(), original)

    def test_failed_write_reports_error_and_does_not_register(self):
        self.registry.fail_write = True
        with self.assertRaises(su.StartupError):
            su.set_startup(True, 'myapp.exe --background')
        self.assertIsNone(su.registered_command())

    def test_launch_command_uses_quoted_exe_path(self):
        with tempfile.TemporaryDirectory(prefix='startup-test-') as folder:
            app = Path(folder) / 'SMSGate Desk.exe'
            app.touch()
            command = su.startup_command(str(app), frozen=True)
            # Windows can expand an 8.3 short temp path (RUNNER~1) to its
            # long form (runneradmin) when Path.resolve() is called.
            # Validate the canonical executable and correct quoting instead.
            expected = subprocess.list2cmdline([str(app.resolve()), su.BACKGROUND_FLAG])
            self.assertEqual(command, expected)
            self.assertTrue(command.startswith('"'), 'EXE path with spaces must be quoted')
            self.assertIn('Enabled for this EXE', su.registration_hint(command, executable=str(app), frozen=True))
            self.assertIn('different copy', su.registration_hint('"C:\\old.exe" --background', executable=str(app), frozen=True))

    def test_prevents_registering_temporary_script_or_missing_exe(self):
        with self.assertRaisesRegex(su.StartupError, 'built'):
            su.startup_command(frozen=False)
        with self.assertRaises(su.StartupError):
            su.startup_command('C:/missing/SMSGateDesk.exe', frozen=True)

    def test_never_modifies_other_startup_programs(self):
        su.set_startup(True, '"C:\\Desk.exe" --background')
        self.assertEqual(self.registry.values['UnrelatedStartupApp'], ('unrelated.exe', self.registry.REG_SZ))
        su.set_startup(False)
        self.assertEqual(len(self.registry.values), 1)


if __name__ == '__main__':
    unittest.main()
