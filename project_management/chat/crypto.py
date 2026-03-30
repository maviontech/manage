import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


ENCRYPTED_PREFIX = "enc::"


def _derive_fallback_key():
    secret = getattr(settings, "SECRET_KEY", "")
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def get_chat_encryption_key():
    configured = getattr(settings, "CHAT_ENCRYPTION_KEY", None)
    if configured:
        return configured.encode("utf-8") if isinstance(configured, str) else configured
    return _derive_fallback_key()


def get_chat_cipher():
    return Fernet(get_chat_encryption_key())


def is_encrypted_chat_text(value):
    return isinstance(value, str) and value.startswith(ENCRYPTED_PREFIX)


def encrypt_chat_text(value):
    if value is None:
        return value
    if not isinstance(value, str):
        value = str(value)
    if is_encrypted_chat_text(value):
        return value
    token = get_chat_cipher().encrypt(value.encode("utf-8")).decode("utf-8")
    return f"{ENCRYPTED_PREFIX}{token}"


def decrypt_chat_text(value):
    if value is None:
        return value
    if not isinstance(value, str):
        return value
    if not is_encrypted_chat_text(value):
        return value
    token = value[len(ENCRYPTED_PREFIX):]
    try:
        return get_chat_cipher().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return "[Encrypted message unavailable]"
