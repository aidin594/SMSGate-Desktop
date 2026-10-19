"""Regression tests for the duplicate-conversation phone formatting defect.

No network requests and no real outgoing SMS are made.
"""
import unittest

from core import all_messages, group_conversations, merge_items, unique_key
from phone_utils import canonical_phone, canonical_display, dialing_number


class PhoneIdentityTests(unittest.TestCase):
    def test_swedish_mobile_many_notations(self):
        formats = [
            '0701234567', '070-123 45 67', '070 1234567',
            '+46701234567', '+46 70 123 45 67',
            '0046701234567', '46701234567',
            '+46 (0)70 123 45 67', '+46 0701234567',
            '0046 (0)70 123 45 67', '70 123 45 67',
            'tel:+46 70 123 45 67', '۰۷۰۱۲۳۴۵۶۷', '070–123–45–67',
        ]
        for number in formats:
            with self.subTest(number=number):
                self.assertEqual(canonical_phone(number, '46'), '46701234567')

    def test_swedish_landline_trunk(self):
        self.assertEqual(canonical_phone('040 12 34 56', '46'), canonical_phone('+46 40 12 34 56', '46'))
        self.assertEqual(canonical_phone('08-123456', '46'), canonical_phone('00468123456', '46'))

    def test_iran_mobile(self):
        formats = ['09121234567', '+989121234567', '00989121234567',
                   '+98 (0)912 1234567', '989121234567', '۰۹۱۲۱۲۳۴۵۶۷']
        self.assertEqual({canonical_phone(x, '98') for x in formats}, {'989121234567'})

    def test_explicit_other_international(self):
        self.assertEqual(canonical_phone('+442012345678'), canonical_phone('00442012345678'))
        self.assertEqual(canonical_phone('+4791234567'), canonical_phone('004791234567'))

    def test_different_numbers_must_not_merge(self):
        numbers = ['0701234567', '0701234568', '+98901234567', '112', '0112', '00112']
        self.assertEqual(len({canonical_phone(x, '46') for x in numbers}), len(numbers))

    def test_short_codes_and_alphanumeric_sender_ids(self):
        self.assertEqual(canonical_phone('ABFA'), canonical_phone('abfa'))
        self.assertNotEqual(canonical_phone('ABFA'), canonical_phone('MCI Shop'))
        self.assertNotEqual(canonical_phone('12345'), canonical_phone('12346'))
        self.assertEqual(dialing_number('ABFA'), '')
        self.assertEqual(dialing_number('112'), '')

    def test_group_incoming_outgoing_same_conversation(self):
        cache = {'inbox': [
            {'id': 'incoming-1', 'phone': '070 123 45 67', 'sim': 2,
             'date': '2026-10-08T12:00:00', 'direction': 'incoming', 'text': 'Hej'},
            {'id': 'incoming-2', 'phone': '0046701234567', 'sim': 2,
             'date': '2026-10-08T12:02:00', 'direction': 'incoming', 'text': 'Hello'},
        ], 'local_sent': [
            {'id': 'send-1', 'phone': '+46701234567', 'sim': 2,
             'date': '2026-10-08T12:01:00', 'direction': 'outgoing', 'text': 'Tack'},
        ], 'sent': []}
        threads = group_conversations(all_messages(cache, 2, country_code='46'), country_code='46')
        self.assertEqual(list(threads), ['46701234567'])
        self.assertEqual(len(threads['46701234567']), 3)
        self.assertEqual({x['direction'] for x in threads['46701234567']}, {'incoming', 'outgoing'})
        self.assertEqual(group_conversations(all_messages(cache, 1, country_code='46'), country_code='46'), {})

    def test_global_contextual_grouping_without_country_setting(self):
        cases = [
            ('0712345678', '+44712345678'),
            ('09121234567', '+989121234567'),
            ('0412345678', '+61412345678'),
            ('0701234567', '+46701234567'),
        ]
        for local, international in cases:
            with self.subTest(local=local):
                messages = [
                    {'phone': local, 'direction': 'outgoing', 'text': 'Hi'},
                    {'phone': international, 'direction': 'incoming', 'text': 'Reply'},
                ]
                grouped = group_conversations(messages)
                self.assertEqual(len(grouped), 1)
                self.assertEqual(len(next(iter(grouped.values()))), 2)

    def test_ambiguous_international_suffix_stays_separate(self):
        messages = [{'phone': number} for number in (
            '0712345678', '+44712345678', '+46712345678')]
        grouped = group_conversations(messages)
        self.assertEqual(len(grouped), 3)

    def test_distinct_explicit_country_codes_never_merge(self):
        grouped = group_conversations([
            {'phone': '+44712345678'}, {'phone': '0046712345678'}])
        self.assertEqual(len(grouped), 2)

    def test_duplicate_sent_message_id_across_formatted_numbers(self):
        old = [{'id': 'same-id', 'phone': '+46701234567', 'sim': 1,
                'direction': 'outgoing', 'date': '2026-10-08', 'text': 'hej', 'state': 'Queued'}]
        new = [{'id': 'same-id', 'phone': '070-123 45 67', 'sim': None,
                'direction': 'outgoing', 'date': '2026-10-08', 'text': '', 'state': 'Delivered'}]
        self.assertEqual(unique_key(old[0], '46'), unique_key(new[0], '46'))
        result = merge_items(old, new, country_code='46')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['state'], 'Delivered')
        self.assertEqual(result[0]['sim'], 1)

    def test_sending_formatted_numbers_is_safely_canonical(self):
        self.assertEqual(dialing_number('070 123 45 67', '46'), '+46701234567')
        self.assertEqual(dialing_number('0046701234567'), '+46701234567')
        self.assertEqual(dialing_number('46701234567', '46'), '+46701234567')
        self.assertEqual(dialing_number('09121234567', '98'), '+989121234567')
        self.assertEqual(dialing_number('invalid-number'), '')
        self.assertEqual(canonical_display('070-123 45 67', '46'), '+46701234567')


if __name__ == '__main__':
    unittest.main()
