from __future__ import annotations

from datetime import datetime, timezone
import unittest

from runtime.gtn_local_product.cadence import parse_cadence, should_run_scheduled_now, start_calendar_intervals


class CadenceTests(unittest.TestCase):
    def test_supported_values(self) -> None:
        self.assertEqual(parse_cadence("15m"), ("15m", 900))
        self.assertEqual(parse_cadence("30m"), ("30m", 1800))
        self.assertEqual(parse_cadence("1h"), ("1h", 3600))
        self.assertEqual(parse_cadence("4h"), ("4h", 14400))
        self.assertEqual(parse_cadence("6h"), ("6h", 21600))
        self.assertEqual(parse_cadence("12h"), ("12h", 43200))
        self.assertEqual(parse_cadence("1d"), ("1d", 86400))

    def test_rejects_unsupported_values(self) -> None:
        with self.assertRaises(ValueError):
            parse_cadence("2h")

    def test_start_calendar_intervals_anchor_four_hour_schedule_to_eight_am(self) -> None:
        self.assertEqual(
            start_calendar_intervals(4 * 60 * 60),
            [
                {"Hour": 0, "Minute": 0},
                {"Hour": 4, "Minute": 0},
                {"Hour": 8, "Minute": 0},
                {"Hour": 12, "Minute": 0},
                {"Hour": 16, "Minute": 0},
                {"Hour": 20, "Minute": 0},
            ],
        )

    def test_should_run_scheduled_now_supports_catchup_window(self) -> None:
        # 2026-04-11 09:00 +08 against 4h anchored slots => missed 08:00, next is 12:00.
        decision = should_run_scheduled_now(
            now_epoch=datetime(2026, 4, 11, 1, 0, tzinfo=timezone.utc).timestamp(),
            cadence_seconds=4 * 60 * 60,
            last_success_epoch=datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc).timestamp(),
        )
        self.assertTrue(decision.should_run)
        self.assertEqual(decision.reason, "catchup_missed_slot")


if __name__ == "__main__":
    unittest.main()
