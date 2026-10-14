"""No actual gateway requests or SMS are sent."""
import sys
import unittest
from unittest.mock import patch

import credential_store as creds


class PasswordStorageTests(unittest.TestCase):
    def test_target_stable_across_windows_builds(self):
        self.assertEqual(creds._target('http://192.168.1.10:8080/'),
                         'SMSGateDeskCommunity:http://192.168.1.10:8080')

    def test_password_never_saved_in_json(self):
        from core import DEFAULT_SETTINGS
        self.assertNotIn('password', DEFAULT_SETTINGS)

    def test_verify_after_write(self):
        with patch.object(creds, '_native_write') as writer, \
             patch.object(creds, '_native_read', return_value='test-pass') as reader:
            creds.save_password('test-server', 'test-pass')
        writer.assert_called_once_with('test-server', 'test-pass')
        reader.assert_called_once_with('test-server')

    def test_reject_bad_readback(self):
        with patch.object(creds, '_native_write'), \
             patch.object(creds, '_native_read', return_value=None):
            with self.assertRaisesRegex(creds.CredentialStoreError, 'not verified'):
                creds.save_password('test-server', 'test-pass')

    def test_reject_empty_password(self):
        with self.assertRaises(creds.CredentialStoreError):
            creds._native_write('test-server', '')

    @unittest.skipUnless(sys.platform == 'win32', 'Native credential tests run on Windows')
    def test_real_windows_credential_round_trip(self):
        # Uses unique, disposable credentials; never touches the gateway password.
        self.assertTrue(creds.credential_self_test())


if __name__ == '__main__':
    unittest.main()
