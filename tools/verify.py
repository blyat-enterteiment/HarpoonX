from pathlib import Path
import subprocess,json,time,hashlib
root=Path(__file__).resolve().parents[1]
commands=[['node','tools/runtime_test.cjs'],['node','tools/cloud_test.cjs'],['node','tools/control_test.cjs'],['node','tools/edge_test.cjs'],['python3','tools/install_test.py'],['node','node_modules/typescript/bin/tsc','--allowJs','--checkJs','--noEmit','--skipLibCheck','--target','ES2022','--module','node16','--types','node','runtime/control.cjs','deploy/managed.cjs']]
report=[]
for cmd in commands:
 start=time.perf_counter();r=subprocess.run(cmd,cwd=root,capture_output=True,text=True);report.append({'command':cmd,'exit_code':r.returncode,'elapsed_ms':round((time.perf_counter()-start)*1000,2),'output':r.stdout+r.stderr})
 if r.returncode:raise SystemExit(json.dumps(report[-1],indent=2))
for path in [*root.glob('runtime/*.cjs'),*root.glob('deploy/*.cjs')]:subprocess.run(['node','--check',str(path)],check=True,capture_output=True)
(root/'evidence/verification.json').write_text(json.dumps({'results':report,'external_orders':0,'paid_model_calls':0,'docker_build_executed':False,'timing_scope':'Test-suite elapsed time, not trading latency or provider benchmark'},indent=2))
print('Verified:',len(commands),'commands; native engines and injected integration tests distinguished in evidence.')
