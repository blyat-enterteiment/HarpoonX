"""Independent Decimal formula verification; does not import JavaScript helpers."""
import json, sys
from decimal import Decimal, localcontext
from pathlib import Path

def D(x): return Decimal(str(x))
def verify(data):
    with localcontext() as ctx:
        ctx.prec = 42
        expected = D(0)
        for x in data["parts"]:
            mu = D(x["muAbsMax"])
            s = D(x["sigmaMaxRegular"])
            drift = mu.exp()
            def delta(sig):
                return 2*drift*((sig*sig).exp()-1).sqrt() + (mu.exp()-1)
            a = D(".996")*delta(s) + D(".004")*delta(4*s)
            fee = D(x["perSideFee"])
            f = D(x["friction"])
            tick = D(x["tick"])
            qty = D(x["quantity"])
            opening = D(x["openingPrice"])
            value = qty*opening*(2*a+f*(1+a)) + qty*(tick*D("1.00000001")+fee)
            reported = D(x["expectedPositiveNativeCreditUpperUsd"])
            assert abs(value-reported) < D("0.000000002"), (value,reported)
            expected+=value
        assert abs(expected-D(data["conditionalExpectedPositiveCreditUpperUsd"])) < D(".000000004")
        assert data["nativeN9SCertificate"] is False
        print("M11_P6_DECIMAL_INDEPENDENT_PASSED", str(expected))

if __name__=="__main__":
    verify(json.loads(Path(sys.argv[1]).read_text()))
