"""Finite-law adversarial tests: no reused generator seeds or economic accounts."""
import unittest
from fractions import Fraction as F

from fwn9_phase9f_tail_bounds import (
    CREDIT_THRESHOLD, Outcome, audit_finite_law, cap_diagnostic,
    rare_near_ruin_law,
)


class TailLemmaTests(unittest.TestCase):
    def test_zero_credit(self):
        a = audit_finite_law([Outcome(F(1), F(19990), F(19990))], F(10000))
        self.assertEqual(a.mean_positive_relative_credit, 0)
        self.assertFalse(a.population_certified)

    def test_previous_p8_witness_is_diagnostic_only(self):
        a = audit_finite_law([Outcome(F(1), F("20112.16"), F("19973.20"))], F(10000))
        self.assertEqual(a.mean_positive_relative_credit, F("138.96") / F("19973.20"))
        self.assertGreater(a.mean_positive_relative_credit, CREDIT_THRESHOLD)
        self.assertFalse(a.population_certified)

    def test_negative_difference_has_zero_positive_credit(self):
        a = audit_finite_law([Outcome(F(1), F("19975.74"), F("19977.06"))], F(10000))
        self.assertEqual(a.mean_positive_relative_credit, 0)

    def test_exact_cauchy_schwarz(self):
        a = audit_finite_law(rare_near_ruin_law(F(1, 2)), F(1))
        self.assertLessEqual(a.mean_positive_relative_credit ** 2, a.cauchy_schwarz_upper_squared)
        self.assertEqual(a.mean_positive_relative_credit, F(1, 512))

    def test_tail_decomposition_reconciles(self):
        a = audit_finite_law(rare_near_ruin_law(F(1, 2)), F(1))
        self.assertEqual(a.head_credit + a.tail_credit, a.mean_positive_relative_credit)
        self.assertEqual(a.head_credit, 0)
        self.assertEqual(a.tail_credit, F(1, 512))
        self.assertLessEqual(a.tail_credit ** 2, a.tail_cauchy_schwarz_upper_squared)

    def test_first_moment_not_sufficient(self):
        earlier = audit_finite_law(rare_near_ruin_law(F(1)), F(2))
        later = audit_finite_law(rare_near_ruin_law(F(1, 2)), F(2))
        self.assertEqual(earlier.mean_positive_difference_usd, later.mean_positive_difference_usd)
        self.assertLess(earlier.mean_positive_relative_credit, CREDIT_THRESHOLD)
        self.assertGreater(later.mean_positive_relative_credit, CREDIT_THRESHOLD)

    def test_inverse_tail_can_be_arbitrarily_large_in_abstract_law(self):
        values = [audit_finite_law(rare_near_ruin_law(F(1, 2**n)), F(1))
                  for n in (2, 6, 12)]
        self.assertLess(values[0].mean_positive_relative_credit, values[1].mean_positive_relative_credit)
        self.assertLess(values[1].mean_positive_relative_credit, values[2].mean_positive_relative_credit)
        self.assertTrue(all(v.mean_positive_difference_usd == F(1, 1024) for v in values))

    def test_cap_after_appreciation_is_not_continuous(self):
        self.assertEqual(cap_diagnostic(F(2400), F(10)), F(24000, 41600))
        self.assertGreater(cap_diagnostic(F(2400), F(10)), F(12, 100))

    def test_invalid_probability_mass_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "PROBABILITIES"):
            audit_finite_law([Outcome(F(1, 2), F(20000), F(20000))], F(1000))

    def test_nonpositive_wealth_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "NONPOSITIVE"):
            audit_finite_law([Outcome(F(1), F(1), F(0))], F(1))

    def test_strict_probability_and_cutoff(self):
        with self.assertRaises(ValueError):
            audit_finite_law([Outcome(F(-1), F(1), F(1)), Outcome(F(2), F(1), F(1))], F(1))
        with self.assertRaises(ValueError):
            audit_finite_law([Outcome(F(1), F(1), F(1))], F(0))

    def test_conditions_not_an_n9_certificate(self):
        a = audit_finite_law(rare_near_ruin_law(F(1)), F(2))
        self.assertTrue(a.numerical_credit_condition)
        self.assertFalse(a.population_certified)


if __name__ == "__main__":
    unittest.main()
