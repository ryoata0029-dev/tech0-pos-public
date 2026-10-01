"""Strict boundaries from requirements 3.6 and API contract 5.2.

Wire money/rates are strings; internal money and basis points are integers.
Never normalize user codes or round an invalid input into a valid value.
"""

import re
from datetime import UTC, datetime

MAX_MONEY = 999_999_999_999
MAX_INTERNAL_ID = 18_446_744_073_709_551_615
RATE_SCALE = 10_000


class ValidationError(ValueError):
    """Invalid input or an amount that cannot be stored/displayed."""


def bounded_integer(value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValidationError("整数の型または範囲が不正です")
    return value


def code(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,32}", value) is None:
        raise ValidationError("コードの形式が不正です")
    return value


def quantity(value: object) -> int:
    return bounded_integer(value, 1, 99)


def money(value: object) -> int:
    return bounded_integer(value, 0, MAX_MONEY)


def parse_money(value: object) -> int:
    if not isinstance(value, str) or re.fullmatch(r"0|[1-9][0-9]{0,11}", value) is None:
        raise ValidationError("円額は範囲内の十進文字列で指定してください")
    return money(int(value))


def parse_internal_id(value: object) -> int:
    if not isinstance(value, str) or re.fullmatch(r"[1-9][0-9]{0,19}", value) is None:
        raise ValidationError("内部IDの形式が不正です")
    return bounded_integer(int(value), 1, MAX_INTERNAL_ID)


def parse_rate(value: object) -> int:
    """Parse an API fraction into exact integer basis points (0..10000)."""
    if (
        not isinstance(value, str)
        or re.fullmatch(r"0(?:\.[0-9]{1,4})?|1(?:\.0{1,4})?", value) is None
    ):
        raise ValidationError("率の範囲または精度が不正です")
    whole, _, fraction = value.partition(".")
    return int(whole) * RATE_SCALE + int(fraction.ljust(4, "0"))


def utc(value: datetime) -> datetime:
    """Require an explicit zone; callers convert Japan-time input via +09:00."""
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValidationError("日時にはタイムゾーンが必要です")
    return value.astimezone(UTC)


def active_period(start: datetime, end: datetime, instant: datetime) -> bool:
    start, end, instant = utc(start), utc(end), utc(instant)
    if start >= end:
        raise ValidationError("期間は開始より終了を後にしてください")
    return start <= instant < end
