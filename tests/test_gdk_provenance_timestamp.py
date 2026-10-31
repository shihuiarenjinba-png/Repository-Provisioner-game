"""Fail-closed tests for the GDK approved-Identity timestamp trust boundary."""
from datetime import datetime, timedelta, timezone
import unittest

from gdk_provenance_timestamp import require_valid_provided_at
from package_identity_provisioner import ConflictError


class GdkProvidedAtTests(unittest.TestCase):
    def test_real_user_timestamp_with_timezone(self):
        for stamp in ("2026-10-28T10:49:00Z", "2026-10-28T19:49:00+09:00",
                      "2026-10-28T10:49:00.123456+00:00"):
            with self.subTest(stamp=stamp):
                self.assertIsNone(require_valid_provided_at(stamp))

    def test_invalid_calendar_or_clock_rejected(self):
        for stamp in ("2026-02-30T10:49:00Z", "2026-13-28T10:49:00Z",
                      "2026-10-28T25:49:00Z", "2026-10-28T10:60:00Z",
                      "2026-10-28T10:49:00+25:00"):
            with self.subTest(stamp=stamp):
                with self.assertRaises(ConflictError):
                    require_valid_provided_at(stamp)

    def test_missing_or_ambiguous_timezone_rejected(self):
        for stamp in ("2026-10-28T10:49:00", "2026-10-28 10:49:00Z",
                      "2026-10-28T10:49:00z", "2026-10-28T10:49:00+0900",
                      "2026-10-28T10:49:00.1234567Z", "", None, True):
            with self.subTest(stamp=stamp):
                with self.assertRaises(ConflictError):
                    require_valid_provided_at(stamp)

    def test_future_operator_timestamp_rejected(self):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        with self.assertRaisesRegex(ConflictError, "future"):
            require_valid_provided_at(future)

    def test_timestamp_is_not_rewritten(self):
        stamp = "2026-10-28T19:49:00+09:00"
        self.assertIsNone(require_valid_provided_at(stamp))
        self.assertEqual(stamp, "2026-10-28T19:49:00+09:00")


if __name__ == "__main__":
    unittest.main()
