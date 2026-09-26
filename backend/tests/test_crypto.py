import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.core.crypto import TokenCipher


def key() -> str:
    return Fernet.generate_key().decode()


def test_roundtrip_does_not_store_plaintext():
    cipher = TokenCipher(SecretStr(key()))
    ciphertext = cipher.encrypt("ig-access-token")
    assert "ig-access-token" not in ciphertext
    assert cipher.decrypt(ciphertext) == "ig-access-token"


def test_rotation_keeps_old_ciphertexts_readable():
    old, new = key(), key()
    ciphertext = TokenCipher(SecretStr(old)).encrypt("token")
    rotated = TokenCipher(SecretStr(f"{new},{old}"))
    assert rotated.decrypt(ciphertext) == "token"
    assert TokenCipher(SecretStr(new)).decrypt(rotated.encrypt("token")) == "token"


def test_wrong_key_fails_cleanly():
    ciphertext = TokenCipher(SecretStr(key())).encrypt("token")
    with pytest.raises(ValueError):
        TokenCipher(SecretStr(key())).decrypt(ciphertext)
