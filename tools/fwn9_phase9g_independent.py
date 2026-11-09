"""Independent high-precision reconciliation of conditional bounds, no shared imports."""
from decimal import Decimal, localcontext
import json


def verify() -> dict[str, str]:
    with localcontext() as ctx:
        ctx.prec = 70
        capital = Decimal("20000")
        min_gate = capital * Decimal(".92")
        residual = Decimal(1) - Decimal(".12") - Decimal(".0025")
        nominal = min_gate * residual - Decimal(176)
        stress = min_gate * residual - Decimal(352)
        gap = (Decimal(1)-Decimal("0.9051232469572758")) * Decimal(176) / 10000
        maximum_delta = nominal * gap
        fixture_cash = Decimal(20000) - Decimal(2000)
        fixture_floor = fixture_cash - Decimal(400) - Decimal(50) - Decimal(176)
        assert nominal == Decimal(15970)
        assert stress == Decimal(15794)
        assert fixture_floor == Decimal(17374)
        assert nominal < fixture_floor
        assert gap == Decimal("0.00166983085355194592")
        assert maximum_delta == Decimal("15970") * gap
        return {"status":"P9G_DECIMAL_70_CONDITIONAL_PROOF_ARITHMETIC_PASS",
                "nominal_conditional_floor_usd":str(nominal),
                "stress_conditional_floor_usd":str(stress),
                "credit_gap":str(gap),
                "required_E_positive_diff_usd_below":str(maximum_delta),
                "m9_native_equivalence_verified":"NO"}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
