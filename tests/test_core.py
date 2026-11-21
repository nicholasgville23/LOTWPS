"""Fast, offline tests for the broadcast primitives (no RF device required)."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from lotwps import audio, same


class BroadcastPrimitiveTests(unittest.TestCase):
    def test_same_header_has_valid_structure(self) -> None:
        issued = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
        header = same.same_header(
            "Tornado Warning",
            ["018089", "018127"],
            issued_utc=issued,
            callsign="WXJ75/NWS",
        )
        self.assertTrue(header.startswith("ZCZC-WXR-"))
        self.assertEqual(same.validate_header(header), [])

    def test_same_burst_contains_three_headers_and_three_eom_bursts(self) -> None:
        issued = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
        bursts = same.same_burst(
            "Tornado Warning",
            ["018089"],
            issued_utc=issued,
            callsign="WXJ75/NWS",
            repeats=3,
        )
        self.assertEqual(len(bursts), 6)
        self.assertTrue(all(len(burst) > 0 for burst in bursts))

    def test_1050_hz_tone_sample_count(self) -> None:
        tone = audio.tone_pcm(1050, 0.1, rate=16000)
        self.assertEqual(len(tone), 1600)


if __name__ == "__main__":
    unittest.main()
