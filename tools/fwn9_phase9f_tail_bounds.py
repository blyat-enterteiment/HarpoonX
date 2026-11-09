"""M11 P9F: exact finite-law moment inequalities, NOT a M9 population certificate."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Sequence

CAPITAL_USD = Fraction(20000)
EVALUATION_DAYS = 176
N9_HURDLE_BP_DAY = Fraction(1)
CONDITIONAL_WEAK_BP_DAY = Fraction("0.9051232469572758")
CREDIT_THRESHOLD = (
    N9_HURDLE_BP_DAY - CONDITIONAL_WEAK_BP_DAY
) * EVALUATION_DAYS / 10000


@dataclass(frozen=True)
class Outcome:
    probability: Fraction
    native_usd: Fraction
    causal_usd: Fraction


@dataclass(frozen=True)
class MomentAudit:
    mean_positive_difference_usd: Fraction
    mean_positive_relative_credit: Fraction
    second_difference_moment_usd2: Fraction
    inverse_causal_second_moment_usd_minus2: Fraction
    cauchy_schwarz_upper_squared: Fraction
    head_credit: Fraction
    head_ceiling: Fraction
    tail_credit: Fraction
    tail_cauchy_schwarz_upper_squared: Fraction
    cutoff_usd: Fraction
    numerical_credit_condition: bool
    population_certified: bool = False


def audit_finite_law(outcomes: Sequence[Outcome], cutoff_usd: Fraction) -> MomentAudit:
    """Exact Cauchy-Schwarz + truncation bounds for a COMPLETE supplied finite law.

    Each row is a mathematical outcome with a declared probability. No sampling,
    market-generator probabilities, trade simulation, or N9 promotion is implied.
    """
    if not outcomes or cutoff_usd <= 0:
        raise ValueError("P9F_EMPTY_OR_INVALID_CUTOFF")
    if any(o.probability < 0 or o.native_usd <= 0 or o.causal_usd <= 0
           for o in outcomes):
        raise ValueError("P9F_INVALID_LAW_OR_NONPOSITIVE_WEALTH")
    if sum((o.probability for o in outcomes), Fraction()) != 1:
        raise ValueError("P9F_PROBABILITIES_NOT_NORMALIZED")

    mean_x = Fraction()
    credit = Fraction()
    second_x = Fraction()
    inverse_second = Fraction()
    head_credit = Fraction()
    head_x = Fraction()
    tail_credit = Fraction()
    tail_second_x = Fraction()
    tail_inverse_second = Fraction()
    for o in outcomes:
        d = max(Fraction(), o.native_usd - o.causal_usd)
        p = o.probability
        mean_x += p * d
        credit += p * d / o.causal_usd
        second_x += p * d * d
        inverse_second += p / (o.causal_usd * o.causal_usd)
        if o.causal_usd < cutoff_usd:
            tail_credit += p * d / o.causal_usd
            tail_second_x += p * d * d
            tail_inverse_second += p / (o.causal_usd * o.causal_usd)
        else:
            head_credit += p * d / o.causal_usd
            head_x += p * d
    overall_cs_sq = second_x * inverse_second
    tail_cs_sq = tail_second_x * tail_inverse_second
    head_ceiling = head_x / cutoff_usd
    if credit * credit > overall_cs_sq:
        raise ArithmeticError("P9F_CAUCHY_SCHWARZ_BREACH")
    if tail_credit * tail_credit > tail_cs_sq:
        raise ArithmeticError("P9F_TAIL_CAUCHY_SCHWARZ_BREACH")
    if head_credit > head_ceiling:
        raise ArithmeticError("P9F_TRUNCATION_HEAD_BREACH")
    if head_credit + tail_credit != credit:
        raise ArithmeticError("P9F_TAIL_SPLIT_NOT_RECONCILED")
    return MomentAudit(
        mean_positive_difference_usd=mean_x,
        mean_positive_relative_credit=credit,
        second_difference_moment_usd2=second_x,
        inverse_causal_second_moment_usd_minus2=inverse_second,
        cauchy_schwarz_upper_squared=overall_cs_sq,
        head_credit=head_credit,
        head_ceiling=head_ceiling,
        tail_credit=tail_credit,
        tail_cauchy_schwarz_upper_squared=tail_cs_sq,
        cutoff_usd=cutoff_usd,
        numerical_credit_condition=credit < CREDIT_THRESHOLD,
        population_certified=False,
    )


def rare_near_ruin_law(causal_low: Fraction, weight: Fraction = Fraction(1, 1024)) -> tuple[Outcome, Outcome]:
    """Abstract diagnostic law, NOT a feasible path distribution from M9."""
    if causal_low <= 0 or weight <= 0 or weight >= 1:
        raise ValueError("P9F_INVALID_DIAGNOSTIC_LAW")
    return (
        Outcome(weight, causal_low + 1, causal_low),
        Outcome(1 - weight, CAPITAL_USD, CAPITAL_USD),
    )


def cap_diagnostic(initial_notional: Fraction, subsequent_multiplier: Fraction) -> Fraction:
    """Long-only post-admission exposure, without assuming a continuous 12% cap."""
    if not 0 <= initial_notional <= CAPITAL_USD * Fraction(12, 100) or subsequent_multiplier <= 0:
        raise ValueError("P9F_INVALID_ADMISSION_DIAGNOSTIC")
    marked = initial_notional * subsequent_multiplier
    equity = CAPITAL_USD + marked - initial_notional
    if equity <= 0:
        raise ValueError("P9F_NONPOSITIVE_DIAGNOSTIC_EQUITY")
    return marked / equity
