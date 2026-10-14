import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path
from core import DEFAULT_SETTINGS, app_dir, validate_url, load_settings, unique_key, merge_items, group_conversations
from credential_store import SERVICE
from startup_utils import VALUE_NAME
from phone_utils import canonical_phone, canonical_display, dialing_number

class CommunityIsolationTests(unittest.TestCase):
    def test_no_private_defaults(self):
        self.assertEqual(DEFAULT_SETTINGS['url'], '')
        self.assertEqual(DEFAULT_SETTINGS['user'], '')
        self.assertEqual(DEFAULT_SETTINGS['country_code'], '')
        self.assertEqual(app_dir().name, 'SMSGateDeskCommunity')
        self.assertEqual(SERVICE, 'SMSGateDeskCommunity')
        self.assertEqual(VALUE_NAME, 'SMSGateDeskCommunity')

    def test_unconfigured_country_never_assumes_sweden(self):
        self.assertEqual(canonical_phone('0701234567'), '0701234567')
        self.assertEqual(canonical_phone('+46701234567'), '46701234567')
        self.assertNotEqual(canonical_phone('0701234567'), canonical_phone('+46701234567'))
        self.assertEqual(dialing_number('0701234567'), '0701234567')

    def test_sweden_and_iran_user_selected(self):
        self.assertEqual(canonical_phone('0701234567', '46'), canonical_phone('+46701234567', '46'))
        self.assertEqual(canonical_phone('09121234567', '98'), canonical_phone('+989121234567', '98'))
        self.assertEqual(dialing_number('0701234567', '46'), '+46701234567')
        self.assertEqual(dialing_number('09121234567', '98'), '+989121234567')

    def test_unrelated_international_country(self):
        self.assertEqual(canonical_phone('02012345678', '44'), '442012345678')
        self.assertEqual(canonical_display('02012345678', '44'), '+442012345678')
        self.assertEqual(dialing_number('02012345678', '44'), '+442012345678')

    def test_italian_significant_trunk_zero(self):
        self.assertEqual(canonical_phone('0612345678', '39'), '390612345678')
        self.assertEqual(canonical_phone('+390612345678', '39'), '390612345678')

    def test_merges_after_country_is_set(self):
        a={'id':'1','phone':'0701234567','direction':'outgoing'}
        b={'id':'1','phone':'+46701234567','direction':'outgoing'}
        self.assertEqual(len(merge_items([a],[b],country_code='46')),1)
        self.assertEqual(len(merge_items([a],[b])),2)
        self.assertEqual(len(group_conversations([a,b],country_code='46')),1)

    def test_country_code_input_is_sanitized(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'settings.json'
            path.write_text('{"country_code":"9999"}')
            self.assertEqual(load_settings(path)['country_code'], '')
            path.write_text('{"country_code":"+46"}')
            self.assertEqual(load_settings(path)['country_code'], '46')

if __name__=='__main__':unittest.main()
