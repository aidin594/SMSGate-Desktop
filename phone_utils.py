"""Privacy-preserving phone-number identities for SMSGate Desk Community.

Explicit international numbers always retain their country code. For local
numbers, a user-selected dialing code can normalize leading-trunk-zero forms;
without a setting, the program does not guess the user's home country.
This is a conservative formatter, not an international numbering database.
"""
from __future__ import annotations

import re
import unicodedata

_INVISIBLE = '\u200b\u200c\u200d\u200e\u200f\u2060\u2066\u2067\u2068\u2069\ufeff'
_SEPARATORS = ' \t\r\n\u00a0\u2009\u202f()-./–—‑−'


def _clean(value) -> str:
    """Convert Persian/Arabic/fullwidth digits to ASCII without changing text IDs."""
    text = ''.join(str(unicodedata.decimal(ch)) if ch.isdecimal() else ch
                   for ch in str(value or ''))
    return ''.join(ch for ch in text if ch not in _INVISIBLE).strip()


def _number_parts(value):
    text = _clean(value)
    # Some contact exports use a 'tel:' URL or phone label.
    text = re.sub(r'^(?:tel|mobile|mobil|phone)\s*:\s*', '', text, flags=re.IGNORECASE)
    # +46 (0)70... means +46 70..., not +46 070...
    text = re.sub(r'\(0\)(?=[\s()./\-]*\d)', '', text)
    # Don't accidentally treat company SMS sender IDs as phone numbers.
    compact = ''.join(ch for ch in text if ch not in _SEPARATORS)
    if compact.startswith('+'):
        if not compact[1:].isascii() or not compact[1:].isdigit():
            return text, None, False
        return text, compact[1:], True
    if compact.isascii() and compact.isdigit():
        # '00' is an international dialing prefix, not part of the country code.
        if compact.startswith('00') and len(compact) >= 9:
            return text, compact[2:], True
        return text, compact, False
    return text, None, False


def canonical_phone(value, country_code: str = '') -> str:
    """Stable conversation key; make no guesses about the user's home country.

    If a country code is configured, normalize local 0-prefixed numbers; all
    other numeric and alphanumeric sender identities are kept distinct.
    """
    text, digits, international = _number_parts(value)
    if not digits:
        return ' '.join(text.casefold().split())
    code = str(country_code).strip().lstrip('+')
    if not re.fullmatch(r'[1-9][0-9]{0,2}', code):
        code = ''
    if international:
        # For a configured country only, tolerate +46 070... imperfect exports.
        # Explicit (0) is stripped earlier in _number_parts.
        if code and code != '39' and digits.startswith(code + '0') and len(digits) >= len(code) + 8:
            return code + digits[len(code)+1:]
        return digits
    if code:
        if digits.startswith(code) and len(digits) >= len(code) + 7:
            return digits
        # Italy uses significant trunk zeros in international numbers.
        if digits.startswith('0') and len(digits) >= 8:
            return code + (digits if code == '39' else digits[1:])
        # Common Swedish mobile exports drop the leading national trunk zero.
        if code == '46' and re.fullmatch(r'7[0-9]{8}', digits):
            return '46' + digits
    return digits


def canonical_display(value, country_code: str = '') -> str:
    """Stable user-visible phone identity, or original alphanumeric sender."""
    text, digits, international = _number_parts(value)
    key = canonical_phone(value, country_code)
    code = str(country_code).strip().lstrip('+')
    if international or (code and key.isascii() and key.isdigit() and key.startswith(code) and len(key) >= len(code)+7):
        return '+' + key
    return text


def dialing_number(value, country_code: str = '') -> str:
    """Return an unambiguous recipient without inferring unknown countries."""
    text, digits, international = _number_parts(value)
    if not digits:
        return ''
    key = canonical_phone(value, country_code)
    if not key.isascii() or not key.isdigit() or not (6 <= len(key) <= 15):
        return ''
    code = str(country_code).strip().lstrip('+')
    if international or (code and key.startswith(code) and len(key) >= len(code)+7):
        return '+' + key
    return digits
