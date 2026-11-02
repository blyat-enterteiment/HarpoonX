#!/usr/bin/env python3
"""Rebuild raw-derived dataset, fixed models and signals after immutable admission."""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
APP=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(APP/'tools'))
import residual_register as reg
import residual_model as model
import residual_data_audit as admission

def read(p): return json.loads(Path(p).read_text())
def digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def write(p,v): Path(p).write_text(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n')
def verify(protocol_path,artifacts=None):
 protocol_path=Path(protocol_path)
 receipt=reg.verify(APP/'evidence/residual_30_18_0/registration',protocol_path,APP/'research/residual_30_18/source_manifest.json')
 protocol=read(protocol_path);dataset_path=APP/protocol['dataset'];data=read(dataset_path)
 rebuilt=admission.build_dataset(dataset_path.parent/'raw',protocol)
 if digest(data)!=digest(rebuilt): raise ValueError('RAW_DATASET_DERIVATION_MISMATCH')
 result={'schema':'HARPOON_RESIDUAL_DERIVATION_VERIFICATION_1','verified':True,'admission_identity_hash':receipt['admission_identity_hash'],
 'raw_dataset_rederived':True,'dataset_payload_sha256':digest(data),'financial_acceptance_allowed':False,'fit_invocations':0}
 if artifacts is not None:
  fitted=model.fit_models(data,protocol);signals=model.generate_signals(data,fitted,protocol)
  checks={'models.json':fitted,'signals.json':signals}
  for name,value in checks.items():
   if digest(value)!=digest(read(Path(artifacts)/name)): raise ValueError('DERIVATION_MISMATCH:'+name)
  result.update(hashes={name:digest(value) for name,value in checks.items()},fit_invocations=fitted['counts']['fit_invocations'])
 return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--protocol',type=Path,default=APP/'research/residual_30_18/protocol.json');p.add_argument('--artifacts',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 write(a.output,verify(a.protocol,a.artifacts));print('RESIDUAL_REGISTERED_RAW_DERIVATIONS_VERIFIED')
if __name__=='__main__':main()
