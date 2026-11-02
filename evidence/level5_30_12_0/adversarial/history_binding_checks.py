"""Read-only checks against preserved local history plus separately labeled mutations."""
from __future__ import annotations
import copy
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
APP=Path(sys.argv[1] if len(sys.argv)>1 else ROOT/'level5_work/HARPOON_XXXUltimate_30_12_0').resolve()
sys.path.insert(0,str(APP/'quant'))
from harpoon_quant.economic_gate_v2 import verify_history

def ref(path):
    path=Path(path).resolve()
    return {'path':path.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def save(name,value):
    target=OUT/name
    target.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    return ref(target)

prior_path=APP/'evidence/integral_30_10_1/economic_readiness.json'
prior=json.loads(prior_path.read_bytes())
journal_path=APP/'quant/economic_experiment/study/optimizer.sqlite3'
con=sqlite3.connect(journal_path.resolve().as_uri()+'?mode=ro',uri=True)
try:head=con.execute('SELECT h FROM optimizer_audit ORDER BY seq DESC LIMIT 1').fetchone()[0]
finally:con.close()
manifest={'schema':'HARPOON_RESEARCH_HISTORY_MANIFEST_2','sources':{'quant_journal':ref(journal_path),'ultimate_registry':ref(APP/'evidence/ultimate/registry.json'),'tp32_report':ref(APP/'evidence/tp32/report.json'),'prior_readiness':ref(prior_path)},'quant_audit_head':head,'historical_source_files':{s['relative_path']:ref(APP/s['relative_path']) for s in prior['provenance']['sources']},'global_deduplicated_total':None,'attempt_identity_map':None}
# This fixture was regenerated in level4. Preserve the exact earlier audited
# bytes rather than silently treating the current file as the historical one.
manifest['historical_source_files']['quant/examples/economic_gate/coordinator_fixture/report.json']=ref(OUT/'retained_30_10_1_economic_gate_report.json')
wal=journal_path.with_name(journal_path.name+'-wal')
if wal.exists() and wal.stat().st_size:
    manifest['quant_journal_wal']=ref(wal)
p={'period':{'test_start':'2030-01-01T00:00:00+00:00','test_end':'2030-04-01T00:00:00+00:00'},'search':{'total_attempts':23}}
tests=[]
def check(name,m,expected,protocol=p):
    source_ref=save(name+'.input.json',m)
    try:
        value=verify_history(source_ref,ROOT,protocol)
        passed=(expected is None and value['global_deduplicated_total'] is None and value['search_coverage_verified'] is False) or (expected=='FRESHNESS_FALSE' and value['test_after_known_history'] is False and value['search_coverage_verified'] is False)
        tests.append({'id':name,'passed':passed,'expected_error':expected,'error':None,'result':value})
    except Exception as exc:
        tests.append({'id':name,'passed':str(exc)==expected,'expected_error':expected,'error':str(exc),'error_type':type(exc).__name__})

check('L5-C1-RETAINED-HISTORY-REMAINS-UNRESOLVED',manifest,None)
clone=copy.deepcopy(manifest)
clone['sources']['ultimate_registry']=save('synthetic_replacement_ultimate.json',{'synthetic_adversarial_mutation':True,'trial':{'slots':18,'protocol':{'schema':'HARPOON-ULTIMATE-PROTOCOL-1'}}})
check('L5-C1-REPLACEMENT-FAMILY-WITH-VALID-HASH',clone,'HISTORICAL_FAMILY_NOT_BOUND_TO_PRIOR_AUDIT')
clone=copy.deepcopy(manifest);clone['global_deduplicated_total']=44
check('L5-C1-INVENTED-GLOBAL-TOTAL',clone,'GLOBAL_COUNT_NOT_DERIVED_FROM_SOURCE_IDENTITIES')
clone=copy.deepcopy(manifest);clone['historical_source_files'].pop(next(iter(clone['historical_source_files'])))
check('L5-C1-OMITTED-PRESERVED-SOURCE',clone,'PRIOR_HISTORY_SOURCE_NOT_BOUND')
clone=copy.deepcopy(manifest)
changed=copy.deepcopy(prior);changed['generated_at']='2025-01-01T00:00:00+00:00'
clone['sources']['prior_readiness']=save('synthetic_replacement_prior.json',changed)
check('L5-C1-BACKDATED-PRIOR-AND-REHASH',clone,'PRIOR_AUDIT_RELEASE_ANCHOR_MISMATCH')
check('L5-C1-OLD-TEST-CANNOT-BECOME-FRESH',manifest,'FRESHNESS_FALSE',{'period':{'test_start':'2026-06-01T00:00:00+00:00','test_end':'2026-09-01T00:00:00+00:00'},'search':{'total_attempts':23}})
result={'scope':'Preserved local history integrity and synthetic mutation checks; no journal writes, financial search or source authenticity claim','source_sha256':hashlib.sha256((APP/'quant/harpoon_quant/economic_gate_v2.py').read_bytes()).hexdigest(),'passed':sum(x['passed'] for x in tests),'total':len(tests),'tests':tests,'production_edits':0,'new_economic_experiments':0,'journal_writes':0}
(OUT/'history_binding_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='tests'},ensure_ascii=False))
for test in tests:print(json.dumps({k:v for k,v in test.items() if k!='result'},ensure_ascii=False))
raise SystemExit(0 if result['passed']==result['total'] else 1)
