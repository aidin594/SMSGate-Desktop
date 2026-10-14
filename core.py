"""Pure, testable domain and storage code for SMSGate Desk Community.
No Qt dependencies: can be verified on machines without a GUI.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import requests
from requests.auth import HTTPBasicAuth
from phone_utils import canonical_phone, canonical_display, dialing_number

LOG = logging.getLogger('smsgatedesk')
DEFAULT_SETTINGS = {
    'url': '', 'user': '', 'interval': 60,
    'sim': 1, 'theme': 'dark', 'remember_password': False, 'country_code': '',
    'include_unknown_sim': False,
    'show_unassigned_sent': True,  # Old SMSGate outgoing messages often lack simNumber.
    'desktop_notifications': True,
    'notification_preview': False,
    'close_to_tray': True,
    'start_with_windows': False,
}


def app_dir() -> Path:
    return Path(os.getenv('LOCALAPPDATA') or (Path.home() / '.local' / 'share')) / 'SMSGateDeskCommunity'


def json_load(path: Path, fallback):
    try:
        if not path.exists():
            return fallback
        content = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(content, type(fallback)):
            raise ValueError('Unexpected JSON root')
        return content
    except (OSError, ValueError, UnicodeError):
        LOG.exception('Unreadable JSON data at %s', path.name)
        # Do not destroy unreadable user data.
        if path.exists():
            try:
                backup = path.with_name(path.name + '.corrupt-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
                shutil.copy2(path, backup)
            except OSError:
                LOG.exception('Unable to preserve corrupt file')
        return fallback


def json_save(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2)
    fd, temp_path = tempfile.mkstemp(dir=path.parent, prefix=path.stem+'-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def load_settings(path: Path):
    stored = json_load(path, {})
    settings = dict(DEFAULT_SETTINGS)
    for key in settings:
        if key in stored:
            settings[key] = stored[key]
    # Guard against invalid or legacy settings crashing UI constructors.
    settings['sim'] = 2 if str(settings['sim']) == '2' else 1
    settings['theme'] = settings['theme'] if settings['theme'] in ('light','dark','system') else 'dark'
    try:
        settings['interval'] = min(3600, max(20, int(settings['interval'])))
    except (ValueError, TypeError):
        settings['interval'] = 60
    settings['country_code'] = str(settings.get('country_code') or '').strip().lstrip('+')
    if not re.fullmatch(r'[1-9][0-9]{0,2}', settings['country_code']):
        settings['country_code'] = ''
    settings['remember_password'] = bool(settings['remember_password'])
    settings['include_unknown_sim'] = bool(settings['include_unknown_sim'])
    settings['show_unassigned_sent'] = bool(settings['show_unassigned_sent'])
    settings['desktop_notifications'] = bool(settings['desktop_notifications'])
    settings['notification_preview'] = bool(settings['notification_preview'])
    settings['close_to_tray'] = bool(settings['close_to_tray'])
    settings['start_with_windows'] = bool(settings['start_with_windows'])
    return settings


def validate_url(url: str) -> str:
    """Allow only private/LAN IPs or local loopback; never ship Basic Auth to web."""
    parsed = urlsplit(url.strip())
    if parsed.scheme not in ('http','https') or not parsed.hostname:
        raise ValueError('Enter a valid http:// or https:// local gateway address.')
    if parsed.username or parsed.password or parsed.query or parsed.fragment or (parsed.path not in ('', '/')):
        raise ValueError('Use only the gateway host and port (without path or credentials).')
    try:
        ip = ipaddress.ip_address(parsed.hostname)
        if not (ip.is_private or ip.is_loopback) or ip.is_link_local:
            raise ValueError('Public IPs and link-local addresses are not allowed.')
    except ValueError as exc:
        if str(parsed.hostname).lower() != 'localhost':
            raise ValueError('Use a local/private IP address, e.g. 192.168.1.10.') from exc
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError('Invalid port number.') from exc
    if port is not None and not (1 <= port <= 65535):
        raise ValueError('Invalid port.')
    return url.strip().rstrip('/')




def normalized_sim(value):
    return int(str(value)) if str(value) in ('1','2') else None


def message_visible(msg, sim: int, include_unknown: bool = False) -> bool:
    slot = normalized_sim(msg.get('sim'))
    return slot == sim or (include_unknown and slot is None)


def iso_date(s) -> str:
    text = str(s or '')
    try:
        dt = datetime.fromisoformat(text.replace('Z','+00:00'))
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt.strftime('%Y-%m-%d %H:%M')
    except (TypeError, ValueError, OverflowError):
        return text[:19]


def normalize_inbox(item: dict) -> dict:
    return {
        'id': str(item.get('id') or ''), 'date': str(item.get('createdAt') or item.get('receivedAt') or ''),
        'phone': str(item.get('sender') or item.get('phoneNumber') or ''),
        'sim': normalized_sim(item.get('simNumber')),
        'text': str(item.get('contentPreview') or item.get('message') or item.get('text') or ''),
        'state': str(item.get('type') or 'SMS'), 'direction': 'incoming',
    }


def sent_message_date(item: dict) -> str:
    """SMSGate /messages may supply timestamps only in the states history.

    Pick the earliest valid event timestamp as the message's original time,
    not the delivery confirmation time. Never invent a timestamp.
    """
    for key in ('createdAt', 'sentAt', 'queuedAt'):
        if item.get(key):
            return str(item[key])
    history = item.get('states')
    if not isinstance(history, dict):
        return ''
    candidates = []
    for value in history.values():
        if not isinstance(value, str):
            continue
        try:
            when = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            candidates.append((when.astimezone(timezone.utc), value))
        except (ValueError, OverflowError):
            continue
    return min(candidates)[1] if candidates else ''


def normalize_sent(item: dict) -> list[dict]:
    text_msg = item.get('textMessage')
    body = text_msg.get('text') if isinstance(text_msg, dict) else item.get('message')
    state = item.get('state', 'Queued')
    if isinstance(state, dict):
        state = state.get('state') or state.get('value') or str(state)
    recipients = item.get('recipients') or []
    numbers = [str(x.get('phoneNumber')) for x in recipients if isinstance(x,dict) and x.get('phoneNumber')]
    if not numbers:
        numbers = [str(x) for x in (item.get('phoneNumbers') or []) if x]
    if not numbers and item.get('phone'):
        numbers = [str(item['phone'])]
    return [{
        'id': str(item.get('id') or ''), 'date': sent_message_date(item),
        'phone': number, 'sim': normalized_sim(item.get('simNumber')),
        'text': str(body or ''), 'state': str(state), 'direction': 'outgoing',
    } for number in numbers]


def _legacy_row(kind, x):
    if not isinstance(x,dict):
        return []
    if kind == 'inbox' and 'direction' not in x and 'createdAt' in x:
        return [normalize_inbox(x)]
    if kind == 'sent' and 'direction' not in x and 'recipients' in x:
        return normalize_sent(x)
    if kind == 'sent' and ',' in str(x.get('phone','')):
        numbers = [n.strip() for n in str(x['phone']).split(',') if n.strip()]
    else:
        numbers = [str(x.get('phone') or '')]
    return [dict(id=str(x.get('id') or ''),date=str(x.get('date') or ''),phone=number,
                 text=str(x.get('text') or ''),sim=normalized_sim(x.get('sim')),
                 state=str(x.get('state') or ''),direction=('incoming' if kind=='inbox' else 'outgoing'))
            for number in numbers if number]


def load_cache(path: Path):
    data = json_load(path, {})
    result = {'inbox': [], 'sent': [], 'local_sent': []}
    for kind in result:
        raw = data.get(kind, [])
        if isinstance(raw, list):
            for item in raw:
                result[kind].extend(_legacy_row('inbox' if kind == 'inbox' else 'sent', item))
    return result


def unique_key(item: dict, country_code: str = ''):
    # ID is scoped by direction and recipient; no cross-SIM phone conflation.
    mid = str(item.get('id','')).strip()
    if mid and not mid.startswith('local-'):
        return (item.get('direction'), mid, canonical_phone(item.get('phone'), country_code))
    return ('fallback', item.get('direction'), canonical_phone(item.get('phone'), country_code),
            str(item.get('date')), str(item.get('text')))


def merge_items(existing: list, latest: list, cap: int = 12000, country_code: str = '') -> list:
    mapping = {}
    for entry in existing + latest:
        if not isinstance(entry,dict) or not entry.get('phone'):
            continue
        k = unique_key(entry, country_code)
        prev = mapping.get(k)
        if prev:
            updated = dict(prev)
            updated.update({field:value for field,value in entry.items() if value not in (None,'')})
            # Preserve known SIM and full text if API returns sparse data.
            if normalized_sim(entry.get('sim')) is None and normalized_sim(prev.get('sim')):
                updated['sim'] = prev['sim']
            if not entry.get('text') and prev.get('text'):
                updated['text'] = prev['text']
            mapping[k] = updated
        else:
            mapping[k] = entry
    return sorted(mapping.values(), key=lambda x: str(x.get('date','')))[-cap:]


def group_conversations(messages: list[dict], country_code: str = '') -> dict[str, list[dict]]:
    """Group all phone notations under one contact without modifying records.

    Keep SIM filtering separate: call with all_messages(cache, selected_sim)
    to avoid mixing the selected SIM's messages with the other SIM.
    """
    groups = {}
    for item in messages:
        if not isinstance(item, dict):
            continue
        number = canonical_phone(item.get('phone'), country_code)
        if not number:
            continue
        groups.setdefault(number, []).append(item)
    return groups


def all_messages(cache, sim: int, include_unknown: bool = False, show_unassigned_sent: bool = True, country_code: str = ''):
    results = []
    for kind in ('inbox','local_sent','sent'):
        results.extend(x for x in cache.get(kind,[]) if isinstance(x,dict))
    # Merge gateway updates before filtering: an API reply can omit simNumber,
    # but a previous local send with the same ID knows the selected SIM.
    results = merge_items([],results,cap=40000,country_code=country_code)
    # The SMSGate /messages schema does not guarantee a simNumber for outgoing
    # messages. They must not disappear merely because a single SIM is chosen.
    # Surface them with SIM unknown, not as belonging to the selected SIM.
    return [x for x in results if message_visible(x, sim, include_unknown)
            or (show_unassigned_sent and x.get('direction') == 'outgoing'
                and normalized_sim(x.get('sim')) is None)]


class GatewayError(Exception):
    pass


class Gateway:
    """Read-only refresh and one-shot send; each worker owns its HTTP session."""
    def __init__(self, base: str, user: str, password: str):
        self.base = validate_url(base)
        if not user or not password:
            raise GatewayError('Enter the gateway username and password in Settings.')
        self.auth = HTTPBasicAuth(user, password)

    def request(self, method: str, route: str, **kwargs):
        # Do not follow redirects with Basic Auth; prevent unintended host switching.
        try:
            resp = requests.request(method, self.base + route, auth=self.auth,
                                    timeout=(3,8), allow_redirects=False, **kwargs)
        except requests.RequestException as exc:
            raise GatewayError('Network problem or request timeout. Check phone and Wi-Fi.') from exc
        if resp.status_code in (301,302,303,307,308):
            raise GatewayError('Gateway returned a redirect; check the configured local address.')
        if resp.status_code in (401,403):
            raise GatewayError(f'HTTP {resp.status_code}: Check gateway credentials/permissions.')
        if resp.status_code >= 400:
            raise GatewayError(f'{route}: HTTP {resp.status_code}')
        try:
            return resp.json()
        except ValueError:
            if resp.status_code in (201, 202, 204) and method.upper() == 'POST':
                # A 202 may mean queued with no JSON body. Never suggest retrying.
                return {'accepted': True, 'status': resp.status_code}
            if resp.status_code == 204:
                return {}
            raise GatewayError(f'Invalid JSON returned by {route}.')

    def health(self):
        return self.request('GET','/health')

    def collection(self, route: str, include_content=False, max_rows=2500):
        result = []
        limit = 200
        # Bound processing and avoid unbounded memory/time if endpoint ignores offset.
        offsets_seen = set()
        for offset in range(0,max_rows,limit):
            params = {'limit':limit,'offset':offset}
            if include_content:
                params['includeContent'] = 'true'
            raw = self.request('GET',route,params=params)
            if isinstance(raw,list):
                items = raw
            elif isinstance(raw,dict):
                items = next((raw[k] for k in ('items','data','messages','results') if isinstance(raw.get(k),list)),None)
            else:
                items = None
            if items is None:
                raise GatewayError(f'{route}: unexpected response structure.')
            if not items:
                break
            marker = (str(items[0].get('id','')) if isinstance(items[0],dict) else str(items[0]))
            if marker in offsets_seen:
                break
            offsets_seen.add(marker)
            result.extend(items)
            if len(items) < limit:
                break
        return result[:max_rows]

    def sync(self):
        result={'health': None, 'inbox': None, 'sent': None, 'errors': {}}
        for name,fn in (
            ('health',self.health),
            ('inbox',lambda:self.collection('/inbox')),
            ('sent',lambda:self.collection('/messages',include_content=True)),
        ):
            try: result[name] = fn()
            except Exception as exc:
                result['errors'][name] = str(exc)
                LOG.exception('Gateway %s failed',name)
        return result

    def send(self, number: str, text: str, sim: int):
        if not re.fullmatch(r'\+?\d{6,16}',number):
            raise GatewayError('Recipient must be 6-16 digits, optionally beginning with +.')
        if not text.strip():
            raise GatewayError('Message cannot be empty.')
        if sim not in (1,2):
            raise GatewayError('Select SIM1 or SIM2 in Settings.')
        payload = {'phoneNumbers':[number], 'textMessage':{'text':text},
                   'withDeliveryReport':True, 'simNumber':sim}
        try:
            # IMPORTANT: never automatically retry POST; timeout may follow accepted send.
            return self.request('POST','/messages',json=payload)
        except GatewayError as exc:
            raise GatewayError(str(exc) + ' Do not retry before checking for a queued message.') from exc
