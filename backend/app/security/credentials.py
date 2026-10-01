import hashlib
import re
import secrets

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

TOKEN = re.compile(r"[A-Za-z0-9_-]{43}", re.ASCII)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(value: str | None) -> bytes | None:
    if value is None or TOKEN.fullmatch(value) is None:
        return None
    return hashlib.sha256(value.encode("ascii")).digest()


class Passwords:
    def __init__(self) -> None:
        self.hasher = PasswordHash(
            (
                Argon2Hasher(
                    time_cost=3,
                    memory_cost=65536,
                    parallelism=4,
                    hash_len=32,
                    salt_len=16,
                ),
            )
        )
        self.dummy = self.hasher.hash(new_token())

    def verify(self, password: str, encoded: str | None) -> bool:
        # Do the same work for a missing ID. Invalid stored hashes propagate as 503.
        matched = self.hasher.verify(password, encoded if encoded is not None else self.dummy)
        return matched and encoded is not None

    def hash(self, password: str) -> str:
        return self.hasher.hash(password)
