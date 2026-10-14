"""Bulk SMS and local template regression tests (no live gateway)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core import (
    Gateway, GatewayError, MAX_RECIPIENTS, json_save, load_templates,
    parse_recipients, validate_template,
)


class RecipientTests(unittest.TestCase):
    def test_comma_semicolon_newline_and_de_duplicate_local_international(self):
        result = parse_recipients(
            '+46701234567, 070 123 45 67;\n+46707654321', '46')
        self.assertEqual(result, ['+46701234567', '+46707654321'])

    def test_valid_single_recipient(self):
        self.assertEqual(parse_recipients('0701234567', '46'), ['+46701234567'])

    def test_reject_malformed_and_empty_as_one_atomic_request(self):
        for value in ['', ' +46701234567 ; customer name', '0701234567,bad']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_recipients(value, '46')

    def test_recipient_limit(self):
        numbers = ','.join(f'+4670000{i:05}' for i in range(MAX_RECIPIENTS+1))
        with self.assertRaisesRegex(ValueError, 'Maximum 20'):
            parse_recipients(numbers, '46')

    def test_bulk_gateway_one_post_with_selected_sim(self):
        gateway = Gateway('http://192.168.1.10:8080', 'sms', 'test-secret')
        response = Mock(status_code=202)
        response.json.return_value = {'id': 'bulk-123'}
        with patch('core.requests.request', return_value=response) as request:
            result = gateway.send_many(['+46701234567', '+46707654321'], 'Hej!', 2)
        self.assertEqual(result['id'], 'bulk-123')
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.kwargs['json']['simNumber'], 2)
        self.assertEqual(request.call_args.kwargs['json']['phoneNumbers'],
                         ['+46701234567', '+46707654321'])

    def test_invalid_bulk_is_never_sent(self):
        gateway = Gateway('http://192.168.1.10:8080', 'sms', 'test-secret')
        with patch.object(gateway, 'request') as req:
            with self.assertRaises(GatewayError):
                gateway.send_many(['+46701234567', 'invalid'], 'Hej!', 1)
            with self.assertRaises(GatewayError):
                gateway.send_many(['+46701234567'] * 2, 'Hej!', 1)
            req.assert_not_called()

    def test_ambiguous_bulk_timeout_not_retried(self):
        from requests.exceptions import ReadTimeout
        gateway = Gateway('http://192.168.1.10:8080', 'sms', 'test-secret')
        with patch('core.requests.request', side_effect=ReadTimeout('timeout')) as req:
            with self.assertRaisesRegex(GatewayError, 'Do not retry'):
                gateway.send_many(['+46701234567', '+46707654321'], 'Hej!', 2)
            self.assertEqual(req.call_count, 1)


class TemplateTests(unittest.TestCase):
    def test_template_save_load_utf8_and_no_credentials(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'templates.json'
            name, body = validate_template(' Bike ready ', 'Hej! Din cykel är klar. 🚲 ')
            json_save(path, {name: body})
            self.assertEqual(load_templates(path)[name], body)
            content = path.read_text(encoding='utf-8')
            self.assertNotIn('password', content)
            self.assertNotIn('phoneNumbers', content)

    def test_templates_do_not_change_when_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'templates.json'
            path.write_text(json.dumps({'Valid': 'Hello', '': 'bad', 'broken': ''}), encoding='utf-8')
            self.assertEqual(load_templates(path), {'Valid': 'Hello'})

    def test_invalid_templates(self):
        with self.assertRaises(ValueError):
            validate_template('  ', 'Hello')
        with self.assertRaises(ValueError):
            validate_template('Name', '')
        with self.assertRaises(ValueError):
            validate_template('Name\nExtra', 'Hello')


if __name__ == '__main__':
    unittest.main()
