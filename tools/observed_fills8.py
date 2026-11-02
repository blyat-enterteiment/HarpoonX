#!/usr/bin/env python3
"""Read broker activities or calibrate linked fills; never submit/cancel orders.

Account exports are PRIVATE local evidence. Do not commit them or credentials.
Market-data-only MCP access cannot supply account activities or causal BBOs.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'quant'))
from harpoon_quant.multiasset import calibrate_fills, stamp


def collect(mode, start, end, transport=None):
    if mode not in ('PAPER','LIVE') or stamp(start)>=stamp(end):
        raise ValueError('MODE_OR_INTERVAL')
    origin='https://paper-api.alpaca.markets' if mode=='PAPER' else 'https://api.alpaca.markets'
    key,secret=os.environ.get('APCA_API_KEY_ID'),os.environ.get('APCA_API_SECRET_KEY')
    if transport is None:
        if not key or not secret:
            raise ValueError('BROKER_READ_CREDENTIALS_REQUIRED')
        def transport(route):
            request=Request(origin+route,headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret},method='GET')
            with urlopen(request,timeout=30) as response:
                raw=response.read(16_000_001)
                if len(raw)>16_000_000:
                    raise ValueError('BROKER_RESPONSE_TOO_LARGE')
                return json.loads(raw)
    rows=[];seen=set();token=None
    for _ in range(100):
        query={'after':start,'until':end,'direction':'asc','page_size':100}
        if token:
            query['page_token']=token
        page=transport('/v2/account/activities?'+urlencode(query))
        if not isinstance(page,list) or len(page)>100:
            raise ValueError('ACTIVITY_PAGE_SCHEMA')
        for r in page:
            identity=r.get('id')
            if not isinstance(identity,str) or not identity or identity in seen:
                raise ValueError('DUPLICATE_ACTIVITY_OR_PAGINATION_LOOP')
            seen.add(identity);rows.append(r)
        if len(page)<100:
            return {'schema':'HARPOON_PRIVATE_BROKER_ACTIVITIES_1','mode':mode,
                    'start':start,'end':end,'origin':origin,'activities':rows,
                    'collected_at':datetime.now(timezone.utc).isoformat(),'complete_pagination':True,
                    'calibration_ready':False,'reason':'REQUIRES_CAUSAL_DECISION_QUOTES_AND_LINKED_EXPLICIT_FEES',
                    'execution_allowed':False}
        token=page[-1]['id']
    raise ValueError('ACTIVITY_PAGE_BUDGET_EXHAUSTED')


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='action',required=True)
    c=sub.add_parser('collect');c.add_argument('--mode',choices=['PAPER','LIVE'],required=True)
    c.add_argument('--start',required=True);c.add_argument('--end',required=True);c.add_argument('--output',type=Path,required=True)
    k=sub.add_parser('calibrate');k.add_argument('--input',type=Path,required=True);k.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    result=collect(args.mode,args.start,args.end) if args.action=='collect' else calibrate_fills(json.loads(args.input.read_text()))
    # Never replace an earlier private receipt. 0600 from creation, not chmod after writing.
    fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps({'saved':True,'execution_allowed':False,'contains_private_account_data':args.action=='collect'}))

if __name__=='__main__':
    main()
