from __future__ import annotations

import unittest

from runtime.gtn_local_product.cadence import parse_cadence


class CadenceTests(unittest.TestCase):
    def test_supported_values(self) -> None:
        self.assertEqual(parse_cadence("15m"), ("15m", 900))
        self.assertEqual(parse_cadence("30m"), ("30m", 1800))
        self.assertEqual(parse_cadence("1h"), ("1h", 3600))
        self.assertEqual(parse_cadence("6h"), ("6h", 21600))
        self.assertEqual(parse_cadence("12h"), ("12h", 43200))
        self.assertEqual(parse_cadence("1d"), ("1d", 86400))

    def test_rejects_unsupported_values(self) -> None:
        with self.assertRaises(ValueError):
            parse_cadence("2h")


if __name__ == "__main__":
    unittest.main()
