import unittest
from datetime import UTC, datetime, timedelta, timezone

from app.services import validation as v


class BoundaryTests(unittest.TestCase):
    def test_tc08_codes_preserve_zeros_and_case(self):
        for value in ("0", "0001", "aA_-", "x" * 32):
            with self.subTest(value=value):
                self.assertEqual(v.code(value), value)

    def test_tc08_invalid_codes(self):
        for value in ("", "x" * 33, " a", "a ", "a\n", "１２", "é", 123, None):
            with self.subTest(value=value), self.assertRaises(v.ValidationError):
                v.code(value)

    def test_tc08_quantity(self):
        for value in (1, 99):
            self.assertEqual(v.quantity(value), value)
        for value in (0, -1, 100, 1.0, "1", True, None):
            with self.subTest(value=value), self.assertRaises(v.ValidationError):
                v.quantity(value)

    def test_tc08_money(self):
        for value in ("0", "999999999999"):
            self.assertEqual(v.parse_money(value), int(value))
        for value in ("-1", "1000000000000", "1.0", "01", "1\n", "+1", "１", 1, True):
            with self.subTest(value=value), self.assertRaises(v.ValidationError):
                v.parse_money(value)

    def test_tc08_rates(self):
        for value, expected in (("0", 0), ("0.0001", 1), ("0.10", 1000), ("1.0000", 10000)):
            self.assertEqual(v.parse_rate(value), expected)
        for value in ("-0.1", "1.0001", "0.00001", "0.10000", "1e-1", ".1", "0.1\n", "NaN", 0.1):
            with self.subTest(value=value), self.assertRaises(v.ValidationError):
                v.parse_rate(value)

    def test_tc08_internal_id(self):
        self.assertEqual(v.parse_internal_id("18446744073709551615"), v.MAX_INTERNAL_ID)
        for value in ("0", "01", "18446744073709551616", "1.0", 1):
            with self.subTest(value=value), self.assertRaises(v.ValidationError):
                v.parse_internal_id(value)

    def test_tc09_japan_time_and_half_open_period(self):
        start = datetime(2026, 9, 30, tzinfo=timezone(timedelta(hours=9)))
        end = start + timedelta(days=1)
        self.assertEqual(v.utc(end), datetime(2026, 9, 30, 15, tzinfo=UTC))
        for instant, expected in (
            (start - timedelta(microseconds=1), False),
            (start, True),
            (start + timedelta(microseconds=1), True),
            (end - timedelta(microseconds=1), True),
            (end, False),
            (end + timedelta(microseconds=1), False),
        ):
            with self.subTest(instant=instant):
                self.assertEqual(v.active_period(start, end, instant), expected)

    def test_tc09_invalid_period_or_missing_zone(self):
        now = datetime(2026, 9, 28, tzinfo=UTC)
        for start, end in ((now, now), (now, now - timedelta(seconds=1))):
            with self.assertRaises(v.ValidationError):
                v.active_period(start, end, now)
        with self.assertRaises(v.ValidationError):
            v.utc(now.replace(tzinfo=None))


if __name__ == "__main__":
    unittest.main()
