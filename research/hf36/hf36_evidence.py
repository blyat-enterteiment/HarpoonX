"""HF36-C: immutable quote receipts, strict coverage and economic eligibility.
Does not mistake observed quotes for broker fills or unknown ORIGINAL for CASH.
"""
import hashlib,json,math
from pathlib import Path
from research.hf36.hf36_events import events
from research.hf36.hf36_book import Book
from research.hf36.hf36_execution import Quote,Method,model_buy

def sha256(data):return hashlib.sha256(data).hexdigest()

def validate_quote_evidence(root,selected=None):
    """Inspect HF18 manifests/pages; require 2-sided quotes for every selected event.
    Missing pages, empty windows, timestamps and invalid prices are hard failures.
    """
    root=Path(root)
    target=events() if selected is None else selected
    report=[]
    for e in target:
        folder=root/e["id"].replace(":","_")
        mf=folder/"manifest.json"
        row={"id":e["id"],"status":"MISSING","bid":None,"ask":None}
        if mf.is_file() and not (folder/"INCOMPLETE_DO_NOT_USE").exists():
            try:
                manifest=json.loads(mf.read_bytes())
                if manifest["symbol"]!=e["symbol"] or manifest["kind"]!="quotes":
                    raise ValueError("MANIFEST_IDENTITY")
                if manifest["start"]!=e["quote_window_start_utc"] or manifest["end"]!=e["quote_window_end_utc"]:
                    raise ValueError("MANIFEST_WINDOW")
                pages=manifest["page_hashes"]
                if len(pages)!=manifest["pages"]:raise ValueError("PAGE_COUNT")
                quotes=[]
                for p in pages:
                    raw=(folder/("page_%05d.json"%p["page"])).read_bytes()
                    if sha256(raw)!=p["sha256"]:raise ValueError("PAGE_HASH")
                    quotes.extend(json.loads(raw)["quotes"])
                if len(quotes)!=manifest["records"]:raise ValueError("RECORD_COUNT")
                from datetime import datetime
                start=datetime.fromisoformat(e["quote_window_start_utc"])
                end=datetime.fromisoformat(e["quote_window_end_utc"])
                valid=[]
                for q in quotes:
                    stamp=datetime.fromisoformat(q["t"].replace("Z","+00:00"))
                    bid,ask=float(q["bp"]),float(q["ap"])
                    if start<=stamp<end and 0<bid<ask and math.isfinite(bid) and math.isfinite(ask):
                        valid.append((stamp,bid,ask))
                if valid:
                    stamp,bid,ask=min(valid)
                    row.update(status="QUOTE_OBSERVED_NOT_FILL",bid=bid,ask=ask,
                               quote_at=stamp.isoformat(),pages=len(pages))
                else:row["status"]="NO_ELIGIBLE_QUOTE"
            except (OSError,KeyError,TypeError,ValueError,IndexError) as exc:
                row["status"]="INVALID_EVIDENCE"
                row["error_type"]=type(exc).__name__
        report.append(row)
    return {"events":len(target),"observed":sum(x["status"]=="QUOTE_OBSERVED_NOT_FILL" for x in report),
            "missing":sum(x["status"]=="MISSING" for x in report),
            "invalid":sum(x["status"]=="INVALID_EVIDENCE" for x in report),
            "complete":bool(target) and all(x["status"]=="QUOTE_OBSERVED_NOT_FILL" for x in report),
            "records":report}

def economic_gate(evidence,original,broker_receipts):
    original_valid=(isinstance(original,dict) and original.get("exact_policy_reconstructed") is True
                    and original.get("verified_source_digest") and original.get("wealth_ledger_reconciled") is True)
    return {"quotes_complete":evidence["complete"],"original_exact":bool(original_valid),
            "broker_receipts_authenticated":bool(broker_receipts),
            "can_certify_real_execution":bool(evidence["complete"] and original_valid and broker_receipts),
            "status":"NO_GO" if not (evidence["complete"] and original_valid and broker_receipts) else "EVIDENCE_READY_REQUIRES_OOS"}
