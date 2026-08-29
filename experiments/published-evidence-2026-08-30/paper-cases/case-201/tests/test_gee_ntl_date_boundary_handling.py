from __future__ import annotations

import sys
import unittest
from datetime import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))

from gee_ntl_date_boundary_handling import (
    determine_first_post_event_local_night,
    exact_date_eligibility,
    inclusive_end_to_exclusive,
    utc_product_date_for_local_night,
)


class MyanmarFirstNightContractTests(unittest.TestCase):
    event_time_utc = "2025-03-28T06:20:52Z"
    timezone_name = "Asia/Yangon"
    candidate_start = time(0, 30)
    candidate_end = time(2, 30)

    def test_event_is_normalized_to_yangon_offset(self) -> None:
        decision = determine_first_post_event_local_night(
            self.event_time_utc, self.timezone_name, self.candidate_start, self.candidate_end
        )
        self.assertEqual(decision.event_time_local, "2025-03-28T12:50:52+06:30")

    def test_first_post_event_local_night_is_next_local_date(self) -> None:
        decision = determine_first_post_event_local_night(
            self.event_time_utc, self.timezone_name, self.candidate_start, self.candidate_end
        )
        self.assertEqual(decision.status, "resolved_after_candidate_window")
        self.assertEqual(decision.local_first_night_date, "2025-03-29")

    def test_local_first_night_maps_to_prior_utc_product_date(self) -> None:
        mapping = utc_product_date_for_local_night(
            "2025-03-29", self.timezone_name, self.candidate_start, self.candidate_end
        )
        self.assertEqual(mapping["candidate_start_utc"], "2025-03-28T18:00:00Z")
        self.assertEqual(mapping["candidate_end_utc"], "2025-03-28T20:00:00Z")
        self.assertEqual(mapping["utc_product_date"], "2025-03-28")
        self.assertEqual(mapping["status"], "resolved_utc_indexed_product_date")

    def test_exact_product_eligibility_has_no_later_date_fallback(self) -> None:
        result = exact_date_eligibility(
            "2025-03-28", {"2025-03-28": False, "2025-03-29": True}
        )
        self.assertEqual(result["status"], "no_eligible_first_night_observation")
        self.assertFalse(result["eligible"])
        self.assertEqual(result["utc_product_date"], "2025-03-28")

    def test_eligible_exact_product_is_retained(self) -> None:
        result = exact_date_eligibility("2025-03-28", {"2025-03-28": True})
        self.assertEqual(result["status"], "eligible_first_night_observation")
        self.assertTrue(result["eligible"])

    def test_single_day_end_is_exclusive_next_day(self) -> None:
        self.assertEqual(inclusive_end_to_exclusive("2025-03-28"), "2025-03-29")


if __name__ == "__main__":
    unittest.main()
