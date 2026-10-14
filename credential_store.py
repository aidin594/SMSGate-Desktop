"""Store SMSGate Desk passwords in native Windows Credential Manager.

Uses Win32 CredReadW/CredWriteW directly, so frozen one-file builds do not
rely on Python keyring plugin discovery. Never writes secrets to settings.json.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from uuid import uuid4

TYPE_GENERIC = 1
PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168
SERVICE = 'SMSGateDeskCommunity'


class CredentialStoreError(RuntimeError):
    pass


class _FILETIME(ctypes.Structure):
    _fields_ = [('dwLowDateTime', wintypes.DWORD), ('dwHighDateTime', wintypes.DWORD)]


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ('Flags', wintypes.DWORD),
        ('Type', wintypes.DWORD),
        ('TargetName', wintypes.LPWSTR),
        ('Comment', wintypes.LPWSTR),
        ('LastWritten', _FILETIME),
        ('CredentialBlobSize', wintypes.DWORD),
        ('CredentialBlob', ctypes.POINTER(ctypes.c_ubyte)),
        ('Persist', wintypes.DWORD),
        ('AttributeCount', wintypes.DWORD),
        ('Attributes', ctypes.c_void_p),
        ('TargetAlias', wintypes.LPWSTR),
        ('UserName', wintypes.LPWSTR),
    ]


def _target(server: str) -> str:
    """Match the previous keyring service/account convention when possible."""
    return SERVICE + ':' + server.strip().rstrip('/')


def _api():
    if sys.platform != 'win32':
        raise CredentialStoreError('Secure password persistence requires Windows.')
    try:
        api = ctypes.WinDLL('Advapi32.dll', use_last_error=True)
        api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.POINTER(ctypes.POINTER(_CREDENTIALW))]
        api.CredReadW.restype = wintypes.BOOL
        api.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
        api.CredWriteW.restype = wintypes.BOOL
        api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        api.CredDeleteW.restype = wintypes.BOOL
        api.CredFree.argtypes = [ctypes.c_void_p]
        api.CredFree.restype = None
        return api
    except (OSError, AttributeError) as exc:
        raise CredentialStoreError('Windows Credential Manager is unavailable.') from exc


def _native_read(server: str) -> str | None:
    api = _api()
    found = ctypes.POINTER(_CREDENTIALW)()
    if not api.CredReadW(_target(server), TYPE_GENERIC, 0, ctypes.byref(found)):
        error = ctypes.get_last_error()
        if error == ERROR_NOT_FOUND:
            return None
        raise CredentialStoreError(f'Windows Credential Manager read failed (code {error}).')
    try:
        entry = found.contents
        if not entry.CredentialBlobSize:
            return None
        data = ctypes.string_at(entry.CredentialBlob, entry.CredentialBlobSize)
        try:
            encoding = 'utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-16-le'
            return data.decode(encoding).rstrip('\x00')
        except UnicodeDecodeError as exc:
            raise CredentialStoreError('Existing Windows credential has invalid encoding.') from exc
    finally:
        api.CredFree(ctypes.cast(found, ctypes.c_void_p))


def _native_write(server: str, password: str):
    if not isinstance(password, str) or not password:
        raise CredentialStoreError('Enter the gateway password first.')
    data = password.encode('utf-16-le')
    if len(data) > 2560:
        raise CredentialStoreError('Password is too long for Windows Credential Manager.')
    blob = ctypes.create_string_buffer(data)
    credential = _CREDENTIALW()
    credential.Flags = 0
    credential.Type = TYPE_GENERIC
    credential.TargetName = _target(server)
    credential.Comment = 'SMSGate Desk local gateway password'
    credential.CredentialBlobSize = len(data)
    credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = PERSIST_LOCAL_MACHINE
    credential.AttributeCount = 0
    credential.Attributes = None
    credential.TargetAlias = None
    credential.UserName = SERVICE
    api = _api()
    if not api.CredWriteW(ctypes.byref(credential), 0):
        code = ctypes.get_last_error()
        raise CredentialStoreError(f'Windows Credential Manager write failed (code {code}).')


def read_password(server: str) -> str | None:
    return _native_read(server)


def save_password(server: str, password: str):
    """Write, then read back and verify before claiming success."""
    _native_write(server, password)
    restored = _native_read(server)
    if restored != password:
        raise CredentialStoreError('Windows did not return the saved password. Save was not verified.')


def delete_password(server: str):
    api = _api()
    if not api.CredDeleteW(_target(server), TYPE_GENERIC, 0):
        code = ctypes.get_last_error()
        if code != ERROR_NOT_FOUND:
            raise CredentialStoreError(f'Windows Credential Manager delete failed (code {code}).')


def credential_self_test():
    """Test the *frozen EXE* against WinCred with an unrelated disposable item."""
    server = 'self-test-' + str(uuid4())
    secret = 'test-' + str(uuid4())
    try:
        save_password(server, secret)
    finally:
        delete_password(server)
    return True
