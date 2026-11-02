"""Discovery must receive declared ETF units without fabricating classifications."""
import unittest

from harpoon_quant.calibration import instrument_metadata


class InstrumentMetadataTests(unittest.TestCase):
    def test_etf_units_and_factor_survive_export(self):
        source = {"book": "etf", "factor": "sp500", "leverage": 3,
                  "multiplier": 1, "step": 1, "minQty": 1, "tick": 0.01,
                  "reference": "SYNTHETIC_METADATA_FIXTURE"}
        result = instrument_metadata(source)
        for key in ("book", "factor", "leverage", "multiplier", "step", "minQty", "tick"):
            self.assertEqual(result[key], source[key])
        self.assertEqual(result["metadata_reference"], source["reference"])
        self.assertEqual(source["book"], "etf")

    def test_missing_metadata_is_explicit_and_does_not_invent_a_factor(self):
        result = instrument_metadata({})
        self.assertEqual(result["book"], "UNCLASSIFIED")
        for key in ("factor", "metadata_reference", "leverage", "multiplier", "step", "minQty", "tick"):
            self.assertIsNone(result[key])

    def test_invalid_units_and_classification_fail_closed(self):
        for field in ("leverage", "multiplier", "step", "minQty", "tick"):
            for value in (0, -1, True, "1", float("nan"), float("inf")):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    instrument_metadata({field: value})
        for value in ({"book": "fund-ish"}, {"factor": ""}, {"reference": 3}):
            with self.subTest(metadata=value), self.assertRaises(ValueError):
                instrument_metadata(value)

    def test_reference_is_not_a_permission_or_a_verification_flag(self):
        result = instrument_metadata({"reference": "unverified", "execution_allowed": True,
                                      "liveApproved": True, "metadata_verified": True})
        self.assertNotIn("execution_allowed", result)
        self.assertNotIn("liveApproved", result)
        self.assertNotIn("metadata_verified", result)


if __name__ == "__main__":
    unittest.main()
