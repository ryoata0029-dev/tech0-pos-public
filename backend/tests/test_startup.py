import copy
import json
import unittest
from datetime import timedelta
from unittest.mock import patch

from support.startup import MemoryRepository, passwords

from app.security.credentials import Passwords, new_token, token_hash
from app.services.errors import PosError
from app.services.login_limit import LoginLimit
from app.services.startup import StartupService


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.repo = MemoryRepository()
        self.passwords = passwords()
        self.service = StartupService(self.repo, self.passwords)

    def login(self, staff="STAFF_A", resume=None):
        return self.service.login(staff, "test-only-input", resume)

    def opened(self):
        auth = self.login().auth_cookie
        resume = self.service.start(auth, None).resume_cookie
        self.service.confirm(auth, resume)
        result = self.service.get_cart(auth, resume, create=True)
        return auth, resume, result

    def error(self, status, callback):
        with self.assertRaises(PosError) as caught:
            callback()
        self.assertEqual(status, caught.exception.status)
        return caught.exception

    def test_cookie_handshake_and_idempotent_cart_creation(self):
        auth = self.login().auth_cookie
        self.assertEqual("UNSTARTED", self.service.inspect_register(auth, None).body["start_state"])
        start = self.service.start(auth, None)
        self.assertIsNone(self.repo.reg["current_cart_id"])
        self.error(409, lambda: self.service.get_cart(auth, start.resume_cookie, create=True))
        self.error(409, lambda: self.service.start(auth, None))
        self.error(403, lambda: self.service.confirm(auth, None))
        self.service.confirm(auth, start.resume_cookie)
        self.assertIsNone(self.service.confirm(auth, start.resume_cookie).resume_cookie)
        first = self.service.get_cart(auth, start.resume_cookie, create=True)
        before = copy.deepcopy(self.repo.contexts)
        second = self.service.get_cart(auth, start.resume_cookie, create=True)
        self.assertEqual(first.body, second.body)
        self.assertEqual(1, len(self.repo.carts))
        self.assertIsNone(second.resume_cookie)
        self.assertEqual(before, self.repo.contexts)

    def test_cookie_loss_and_wrong_owner_do_not_replace_context(self):
        auth, resume, result = self.opened()
        before = copy.deepcopy(self.repo.reg)
        self.error(403, lambda: self.login(resume=None))
        self.error(403, lambda: self.login("STAFF_B", resume))
        self.error(403, lambda: self.service.get_cart(auth, new_token(), create=True))
        self.assertEqual(before, self.repo.reg)
        self.assertEqual("[]", self.repo.limits["STAFF_B"]["failure_times"])

    def test_missing_register_and_lost_cart_pointer_stop(self):
        self.repo.reg = None
        self.error(503, lambda: self.login())
        self.setUp()
        auth, resume, result = self.opened()
        self.repo.reg["current_cart_id"] = None
        self.error(503, lambda: self.service.get_cart(auth, resume, create=True))
        self.assertEqual(1, len(self.repo.carts))

    def test_session_rotation_expiry_and_no_resume_extension(self):
        old, resume, result = self.opened()
        context_before = copy.deepcopy(self.repo.contexts)
        self.repo.clock += timedelta(hours=8) - timedelta(microseconds=1)
        self.service.status(old)
        self.repo.clock += timedelta(microseconds=1)
        self.error(401, lambda: self.service.status(old))
        fresh = self.login(resume=resume).auth_cookie
        self.service.status(fresh)
        self.error(401, lambda: self.service.status(old))
        self.assertEqual(context_before, self.repo.contexts)
        self.assertEqual(result.body, self.service.get_cart(fresh, resume).body)

    def test_reauthentication_only_changes_session_for_all_cart_states(self):
        auth, resume, result = self.opened()
        for state in ["EDITING", "SAVING", "UNSAVED", "SAVED"]:
            self.repo.carts[result.body["cart"]["cart_id"]]["state"] = state
            before = copy.deepcopy(self.repo.carts)
            current = self.login(resume=resume).auth_cookie
            self.service.status(current)
            self.assertEqual(before, self.repo.carts)

    def test_resume_24_hour_boundary_and_manual_release(self):
        auth, resume, result = self.opened()
        self.repo.clock += timedelta(hours=24) - timedelta(microseconds=1)
        fresh = self.login(resume=resume).auth_cookie
        self.service.get_cart(fresh, resume)
        self.repo.clock += timedelta(microseconds=1)
        self.error(409, lambda: self.service.get_cart(fresh, resume, create=True))
        self.error(409, lambda: self.login(resume=resume))
        context = self.repo.contexts[self.repo.reg["active_context_id"]]
        old_time = context["last_business_at"]
        context["manual_released_at"] = self.repo.clock
        self.service.get_cart(fresh, resume)
        self.assertEqual(old_time, context["last_business_at"])

    def test_pending_cookie_survives_reauthentication(self):
        auth = self.login().auth_cookie
        resume = self.service.start(auth, None).resume_cookie
        self.repo.clock += timedelta(hours=8)
        auth = self.login(resume=resume).auth_cookie
        self.service.confirm(auth, resume)
        self.assertEqual(1, len(self.repo.contexts))
        self.assertEqual(0, len(self.repo.carts))

    def test_fifth_failure_locks_without_extending_or_revoking_session(self):
        auth = self.login().auth_cookie
        for _ in range(5):
            self.assertIsNone(self.service.login("STAFF_A", "wrong", None))
        limit = copy.deepcopy(self.repo.limits["STAFF_A"])
        calls = self.passwords.verify.call_count
        self.assertIsNone(self.login())
        self.assertEqual(calls, self.passwords.verify.call_count)
        self.assertEqual(limit, self.repo.limits["STAFF_A"])
        self.service.status(auth)
        self.repo.clock += timedelta(minutes=10) - timedelta(microseconds=1)
        self.assertIsNone(self.login())
        self.repo.clock += timedelta(microseconds=1)
        self.assertIsNotNone(self.login())
        self.assertEqual("[]", self.repo.limits["STAFF_A"]["failure_times"])

    def test_success_does_not_clear_failures_and_window_excludes_lower_endpoint(self):
        self.service.login("STAFF_A", "wrong", None)
        self.login()
        self.assertEqual(1, len(json.loads(self.repo.limits["STAFF_A"]["failure_times"])))
        self.repo.clock += timedelta(minutes=10)
        self.service.login("STAFF_A", "wrong", None)
        self.assertEqual(1, len(json.loads(self.repo.limits["STAFF_A"]["failure_times"])))

    def test_missing_staff_is_limited_and_hash_error_is_not_a_failure(self):
        for _ in range(5):
            self.assertIsNone(self.service.login("MISSING", "wrong", None))
        self.assertIsNotNone(self.repo.limits["MISSING"]["locked_until"])
        self.assertIsNotNone(self.login())
        before = copy.deepcopy(self.repo.limits)
        self.passwords.verify.side_effect = ValueError("sensitive hash")
        self.error(503, lambda: self.login())
        self.assertEqual(before, self.repo.limits)

    def test_maintenance_allows_auth_and_reads_but_blocks_writes(self):
        auth, resume, result = self.opened()
        self.repo.reg["maintenance_hold"] = True
        auth = self.login(resume=resume).auth_cookie
        self.service.get_cart(auth, resume)
        self.error(409, lambda: self.service.confirm(auth, resume))
        self.error(409, lambda: self.service.get_cart(auth, resume, create=True))

    def test_other_cart_id_and_nonempty_later_milestone_fail_closed(self):
        auth, resume, result = self.opened()
        self.error(403, lambda: self.service.get_cart(auth, resume, cart_id="other"))
        with patch.object(self.repo, "lines", return_value=[{"name": "preserved"}]):
            self.error(409, lambda: self.service.get_cart(auth, resume))
        self.assertEqual(1, len(self.repo.carts))

    def test_limit_corruption_is_not_silently_reset(self):
        for value in ["{}", "[null]", '["2026-09-28T00:00:00"]', "[1]", "invalid"]:
            self.error(503, lambda value=value: LoginLimit.parse(value, None))

    def test_argon2_and_token_parameters(self):
        passwords = Passwords()
        encoded = passwords.hash("test-only-input")
        self.assertIn("$argon2id$v=19$m=65536,t=3,p=4$", encoded)
        self.assertTrue(passwords.verify("test-only-input", encoded))
        self.assertFalse(passwords.verify("wrong", encoded))
        self.assertFalse(passwords.verify("test-only-input", None))
        token = new_token()
        self.assertEqual(43, len(token))
        self.assertEqual(32, len(token_hash(token)))
        self.assertNotEqual(token, new_token())
        self.assertIsNone(token_hash(token + "\n"))

    def test_auth_cookie_age_counts_time_spent_persisting_session(self):
        with patch("app.services.startup.time.monotonic", return_value=123.0):
            result = self.login()
        self.assertEqual(123.0, result.issued_at)
