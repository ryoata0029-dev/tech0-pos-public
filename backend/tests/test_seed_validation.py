import unittest

from app.services.seed_validation import validate_member


class MemberSeedTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(
            member_id="MEMBER_0",
            name="架空名",
            phone="架空電話",
            address="架空住所",
            gender="自由記述",
            age=0,
        )

    def test_six_attributes_and_unsigned_integer_boundaries(self):
        validate_member(self.row)
        validate_member({**self.row, "age": 4294967295})
        for key in self.row:
            missing = self.row.copy()
            del missing[key]
            for candidate in [missing, {**self.row, key: None}]:
                with self.assertRaises(ValueError):
                    validate_member(candidate)
        for value in [-1, 1.1, True, "1", 4294967296]:
            with self.assertRaises(ValueError):
                validate_member({**self.row, "age": value})

    def test_text_capacity_measured_in_utf8_bytes_and_no_gender_enum(self):
        validate_member({**self.row, "gender": "任意の記述"})
        validate_member({**self.row, "name": "a" * 65535})
        for key in ["name", "phone", "address", "gender"]:
            for value in ["", "a" * 65536, "あ" * 21846]:
                with self.assertRaises(ValueError):
                    validate_member({**self.row, key: value})
