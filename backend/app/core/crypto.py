from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from pydantic import SecretStr


class TokenCipher:
    """Application-level encryption for third-party credentials stored in PostgreSQL.

    Fernet (AES-128-CBC + HMAC-SHA256). Keys come from TOKEN_ENCRYPTION_KEYS; the first key
    encrypts and every listed key can decrypt, so keys can be rotated without downtime.
    """

    def __init__(self, keys: SecretStr) -> None:
        parsed = [k.strip() for k in keys.get_secret_value().split(",") if k.strip()]
        if not parsed:
            raise ValueError("TOKEN_ENCRYPTION_KEYS is empty")
        self._fernet = MultiFernet([Fernet(k) for k in parsed])

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("Stored credential could not be decrypted") from exc
