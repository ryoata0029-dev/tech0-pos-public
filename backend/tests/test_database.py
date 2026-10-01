import unittest
from unittest.mock import MagicMock

from sqlalchemy.exc import OperationalError

from app.infrastructure.database import transaction
from app.services.errors import PosError


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.engine = MagicMock()
        self.connection = self.engine.connect.return_value.__enter__.return_value

    def test_read_snapshot_is_readonly_rr_and_rolled_back_before_return(self):
        with transaction(self.engine, readonly=True) as connection:
            self.assertIs(connection, self.connection)
        self.connection.execution_options.assert_called_once_with(isolation_level="REPEATABLE READ")
        self.connection.exec_driver_sql.assert_called_once_with("START TRANSACTION READ ONLY")
        self.connection.rollback.assert_called_once()
        self.connection.commit.assert_not_called()

    def test_write_commit_failure_invalidates_and_never_replays(self):
        self.connection.commit.side_effect = OperationalError("SQL", {}, Exception("PRIVATE"))
        count = 0
        with self.assertRaises(PosError) as caught:
            with transaction(self.engine):
                count += 1
        self.assertEqual(503, caught.exception.status)
        self.assertNotIn("PRIVATE", str(caught.exception))
        self.assertEqual(1, count)
        self.engine.connect.assert_called_once()
        self.connection.rollback.assert_called_once()
        self.connection.invalidate.assert_called_once()

    def test_business_rejection_rolls_back_without_commit(self):
        with self.assertRaises(ValueError):
            with transaction(self.engine):
                raise ValueError("rejected")
        self.connection.rollback.assert_called_once()
        self.connection.commit.assert_not_called()
