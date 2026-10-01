"""Pure 10-minute rolling window; called under REGISTER -> AUTH_LOGIN_LIMIT locks."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.services.errors import unavailable


@dataclass(frozen=True)
class LoginLimit:
    failures: tuple[datetime, ...]
    locked_until: datetime | None

    @classmethod
    def parse(cls, raw: str, locked_until: datetime | None) -> "LoginLimit":
        try:
            values = json.loads(raw)
            if not isinstance(values, list) or len(values) > 5:
                raise ValueError
            times = tuple(datetime.fromisoformat(value) for value in values)
            if any(t.tzinfo is None or t.utcoffset() != timedelta(0) for t in times):
                raise ValueError
            if tuple(sorted(times)) != times:
                raise ValueError
            return cls(tuple(t.replace(tzinfo=None) for t in times), locked_until)
        except (TypeError, ValueError):
            raise unavailable() from None

    def at(self, now: datetime) -> "LoginLimit":
        if self.locked_until is not None:
            if now < self.locked_until:
                return self
            return LoginLimit((), None)
        if any(t > now for t in self.failures):
            raise unavailable()
        return LoginLimit(tuple(t for t in self.failures if now - timedelta(minutes=10) < t), None)

    def failed(self, now: datetime) -> "LoginLimit":
        failures = (*self.failures, now)
        if len(failures) > 5:
            raise unavailable()
        return LoginLimit(failures, now + timedelta(minutes=10) if len(failures) == 5 else None)

    def json(self) -> str:
        return json.dumps(
            [t.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z") for t in self.failures]
        )
