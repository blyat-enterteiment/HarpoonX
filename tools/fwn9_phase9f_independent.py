"""Independent Decimal-70 moments, no imports from the tested implementation."""
from decimal import Decimal, localcontext
import json


def verify() -> dict[str, str]:
    with localcontext() as context:
        context.prec = 70
        p = Decimal(1) / Decimal(1024)
        c = Decimal("0.5")
        d = Decimal(1)
        mean_delta = p * d
        mean_credit = p * d / c
        ex2 = p * d * d
        e_inv2 = p / c**2 + (1-p) / Decimal(20000)**2
        cs2 = ex2 * e_inv2
        gap = (Decimal(1)-Decimal("0.9051232469572758")) * 176 / 10000
        assert mean_delta == Decimal(1)/Decimal(1024)
        assert mean_credit == Decimal(1)/Decimal(512)
        assert mean_credit**2 <= cs2
        assert gap == Decimal("0.00166983085355194592")
        assert mean_credit > gap
        # Head: large C, delta=0. Tail: rare near-ruin event.
        assert p*d/c == mean_credit
        return {"status": "DECIMAL_70_INDEPENDENT_PASS", "abstract_mean_credit": str(mean_credit),
                "abstract_mean_delta_usd": str(mean_delta), "cauchy_squared": str(cs2),
                "required_gap": str(gap), "m9_population_claim": "NONE"}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
