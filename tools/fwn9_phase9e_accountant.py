"""M11 P9E independent Decimal arithmetic: engineering numbers, not market outcomes."""
from decimal import Decimal, localcontext


def verify() -> dict[str, str]:
    with localcontext() as ctx:
        ctx.prec = 60
        initial = Decimal("20000")
        n = Decimal("20112.16")
        c = Decimal("19973.20")
        differential = n-c
        credit = differential/c
        logarithm = (n/c).ln()
        threshold = Decimal("1")-Decimal("0.9051232469572758")
        per_day_bp = credit * Decimal("10000")/Decimal("176")
        assert n-initial == Decimal("112.16")
        assert c-initial == Decimal("-26.80")
        assert logarithm < credit
        assert per_day_bp > threshold
        assert threshold == Decimal("0.0948767530427242")
        return {"delta_usd":str(differential),"credit_relative":str(credit),
                "log_ratio":str(logarithm),"credit_bp_per_day":str(per_day_bp),
                "hurdle_gap_bp_per_day":str(threshold),
                "status":"PASS_DECIMAL_60_CONDITIONAL_ONLY"}

if __name__=="__main__":
    import json
    print(json.dumps(verify(),indent=2))
