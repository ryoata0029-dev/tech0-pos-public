"""In-memory test double only. This does NOT simulate MySQL locks or constraints."""

import copy
from datetime import datetime
from unittest.mock import Mock

from app.repositories.startup import StartupRepository
from app.security.credentials import Passwords


class MemoryRepository(StartupRepository):
    def __init__(self):
        self.clock = datetime(2026, 9, 28, 0, 0)
        self.reg = dict(
            register_id=1,
            start_state="UNSTARTED",
            maintenance_hold=False,
            active_context_id=None,
            current_cart_id=None,
            active_session_hash=None,
        )
        self.limits = {}
        self.sessions = {}
        self.contexts = {}
        self.carts = {}
        self.staff = {"STAFF_A": "hash-a", "STAFF_B": "hash-b"}

    def register(self, *, lock):
        return copy.deepcopy(self.reg)

    def now(self):
        return self.clock

    def limit(self, staff_id):
        return self.limits.setdefault(
            staff_id, {"failure_times": "[]", "locked_until": None}
        ).copy()

    def save_limit(self, staff_id, failures, until):
        self.limits[staff_id] = {"failure_times": failures, "locked_until": until}

    def password(self, staff_id):
        return self.staff.get(staff_id)

    def session(self, token):
        return self.sessions.get(token)

    def rotate_session(self, staff_id, token, old, now, expires):
        if old in self.sessions:
            self.sessions[old]["revoked_at"] = now
        self.sessions[token] = dict(
            staff_id=staff_id, register_id=1, created_at=now, expires_at=expires, revoked_at=None
        )
        self.reg["active_session_hash"] = token

    def context(self, context_id):
        return copy.deepcopy(self.contexts.get(context_id))

    def start(self, context_id, staff_id, token, now):
        self.contexts[context_id] = dict(
            context_id=context_id,
            register_id=1,
            starting_staff_id=staff_id,
            token_hash=token,
            created_at=now,
            confirmed_at=None,
            last_business_at=None,
            manual_released_at=None,
            invalidated_at=None,
        )
        self.reg.update(start_state="COOKIE_PENDING", active_context_id=context_id)

    def confirm(self, context_id, now):
        self.contexts[context_id]["confirmed_at"] = now
        self.reg["start_state"] = "READY"

    def cart(self, cart_id, *, lock=False):
        return copy.deepcopy(self.carts.get(cart_id))

    def create_cart(self, cart_id, context_id, staff_id, now):
        self.carts[cart_id] = dict(
            cart_id=cart_id,
            context_id=context_id,
            staff_id=staff_id,
            register_id=1,
            state="EDITING",
            version=1,
            member_state="UNSPECIFIED",
            member_id=None,
            pending_member_id=None,
            active_member_operation_id=None,
            active_purchase_operation_id=None,
            purchase_prepared_version=None,
            subtotal=0,
            total=0,
            tax_breakdown="[]",
        )
        self.reg["current_cart_id"] = cart_id
        self.contexts[context_id]["last_business_at"] = now

    def lines(self, cart_id):
        return []

    def purchase(self, cart_id):
        return None


def passwords():
    instance = Mock(spec=Passwords)
    instance.verify.side_effect = lambda password, encoded: (
        encoded is not None and password == "test-only-input"
    )
    return instance
