"""Environment-only configuration; no loading of existing local secret files."""

import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    origin: str
    relay_secret: str = field(repr=False)
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str = field(repr=False)
    db_ca: str

    @classmethod
    def from_env(cls) -> "Settings":
        def required(name: str) -> str:
            value = os.environ.get(name, "")
            if not value:
                raise ValueError("Required POS configuration is missing")
            return value

        origin = required("POS_FRONTEND_ORIGIN")
        parts = urlsplit(origin)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or parts.path
        ):
            raise ValueError("POS origin must be an exact HTTPS origin without a path")
        secret = required("POS_RELAY_SECRET")
        if len(secret) < 32 or not secret.isascii():
            raise ValueError("Relay secret must contain at least 32 ASCII characters")
        return cls(
            origin,
            secret,
            required("POS_DB_HOST"),
            int(os.environ.get("POS_DB_PORT", "3306")),
            required("POS_DB_NAME"),
            required("POS_DB_USER"),
            required("POS_DB_PASSWORD"),
            required("POS_DB_SSL_CA"),
        )
