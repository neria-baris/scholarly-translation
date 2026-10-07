"""Opt-in persistent storage for provider API keys.

Keys the user explicitly asks to remember are kept in the Windows Credential
Manager (encrypted by Windows for the current user account), never in project
files, job files, the browser or logs. Other platforms report no store, so the
UI keeps its memory-only behaviour there.
"""

from __future__ import annotations

import sys

TARGET_PREFIX = "ScholarlyTranslation/provider/"
_MAX_BLOB_BYTES = 2560  # CRED_MAX_CREDENTIAL_BLOB_SIZE


class KeyStoreError(OSError):
    pass


class WindowsCredentialStore:
    """Generic credentials named ``ScholarlyTranslation/provider/<provider_id>``."""

    def __init__(self, prefix: str = TARGET_PREFIX):
        import ctypes
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

        class CREDENTIALW(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                ("LastWritten", FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR),
            ]

        self._ctypes = ctypes
        self._CREDENTIALW = CREDENTIALW
        self._prefix = prefix
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        pcred = ctypes.POINTER(CREDENTIALW)
        self._write = advapi.CredWriteW
        self._write.argtypes = [pcred, wintypes.DWORD]
        self._write.restype = wintypes.BOOL
        self._delete = advapi.CredDeleteW
        self._delete.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self._delete.restype = wintypes.BOOL
        self._enumerate = advapi.CredEnumerateW
        self._enumerate.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                    ctypes.POINTER(ctypes.POINTER(pcred))]
        self._enumerate.restype = wintypes.BOOL
        self._free = advapi.CredFree
        self._free.argtypes = [ctypes.c_void_p]
        self._free.restype = None

    def _error(self, action: str) -> KeyStoreError:
        code = self._ctypes.get_last_error()
        return KeyStoreError(f"מנהל האישורים של Windows: {action} נכשל (קוד {code}).")

    def load_all(self) -> dict[str, str]:
        ctypes = self._ctypes
        count = ctypes.c_ulong(0)
        array = ctypes.POINTER(ctypes.POINTER(self._CREDENTIALW))()
        if not self._enumerate(self._prefix + "*", 0, ctypes.byref(count), ctypes.byref(array)):
            if ctypes.get_last_error() == 1168:  # ERROR_NOT_FOUND
                return {}
            raise self._error("קריאה")
        try:
            result = {}
            for index in range(count.value):
                credential = array[index].contents
                if credential.Type != 1 or not credential.TargetName.startswith(self._prefix):
                    continue
                blob = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
                try:
                    result[credential.TargetName[len(self._prefix):]] = blob.decode("utf-8")
                except UnicodeDecodeError:
                    continue
            return result
        finally:
            self._free(array)

    def save(self, provider_id: str, key: str) -> None:
        ctypes = self._ctypes
        blob = key.encode("utf-8")
        if len(blob) > _MAX_BLOB_BYTES:
            raise KeyStoreError("המפתח ארוך מדי לשמירה במנהל האישורים של Windows.")
        buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        credential = self._CREDENTIALW()
        credential.Type = 1  # CRED_TYPE_GENERIC
        credential.TargetName = self._prefix + provider_id
        credential.Comment = "Scholarly Translation API key"
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE: this user, this computer
        credential.UserName = provider_id
        if not self._write(ctypes.byref(credential), 0):
            raise self._error("שמירה")

    def delete(self, provider_id: str) -> None:
        if not self._delete(self._prefix + provider_id, 1, 0) and self._ctypes.get_last_error() != 1168:
            raise self._error("מחיקה")


def default_key_store():
    """The platform store, or None where persistent keys are not supported."""
    if sys.platform != "win32":
        return None
    try:
        return WindowsCredentialStore()
    except (OSError, AttributeError):
        return None
