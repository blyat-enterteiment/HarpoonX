"""HF25 immutable event reconstruction for all HF24-B executed candidate selections.
Historical development cohort only. No November 2026 holdout or order API.
"""
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from research.hf24.hf24_asset_hypotheses import (
    load, candidate_features, policy_signal, STOCKS, START, END, MAX_POSITIONS,
)

def reconstruct():
    dates,data,source_sha=load()
    histories=defaultdict(list)
    events=[]
    for day in dates:
        selected=[]
        for symbol,bar in data[day].items():
            features=candidate_features(histories[symbol])
            if features and policy_signal("STOCK_VOLUME_BREAKOUT",symbol,features):
                selected.append((symbol,bar,features))
        if START<=day<=END:
            for symbol,bar,features in sorted(selected,key=lambda x:x[0])[:MAX_POSITIONS]:
                events.append({"symbol":symbol,"date":day,
                  "signal_known_at":"PREVIOUS_SESSION_CLOSE",
                  "entry_target":"NEXT_SESSION_OPEN_NOT_YET_EXECUTABLE",
                  "exit_target":"SAME_SESSION_CLOSE_NOT_YET_EXECUTABLE",
                  "daily_open":bar["open"],"daily_close":bar["close"],
                  "mom5":features["mom5"],"mom20":features["mom20"],
                  "rvol":features["rvol"],"break20":features["break20"]})
        for symbol,bar in data[day].items():
            histories[symbol].append(bar)
    if len(events)!=38:
        raise ValueError("Expected exactly 38 previously reported opportunities, got %d" % len(events))
    if len({(e["date"],e["symbol"]) for e in events})!=len(events):
        raise ValueError("Duplicate event")
    manifest={"phase":"HF25","status":"DEVELOPMENT_EVENTS_FROZEN",
      "source_sha256":source_sha,"count":len(events),
      "holdout_november_2026_opened":False,
      "entry_exit_quote_execution":"NOT_PROVEN",
      "events_sha256":hashlib.sha256(json.dumps(events,sort_keys=True,separators=(",",":")).encode()).hexdigest()}
    return manifest,events

if __name__=="__main__":
    manifest,events=reconstruct()
    print("HF25_EVENT_MANIFEST "+json.dumps(manifest,sort_keys=True),flush=True)
    for e in events:
        print("HF25_EVENT "+json.dumps(e,sort_keys=True),flush=True)
