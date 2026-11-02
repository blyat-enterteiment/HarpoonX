"""Reproducible local verification. Requires npm ci and requirements-qa.txt."""
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
commands = [
    ['npm', 'test'],
    ['node', 'tools/auth_security_test.cjs'],
    [sys.executable, '-m', 'unittest', 'discover', '-s', 'service', '-p', 'test_*.py'],
    ['npm', 'run', 'typecheck'],
    [sys.executable, '-m', 'mypy', '--follow-imports=silent', '--check-untyped-defs',
     'service/server.py', 'service/app24.py', 'deploy/configure.py'],
    [sys.executable, '-m', 'ruff', 'check', '--select', 'F821,F822,F823', 'service', 'runtime', 'deploy'],
    [sys.executable, '-m', 'compileall', '-q', 'service', 'runtime', 'deploy', 'tools'],
    ['node', 'tools/auth_benchmark.cjs'],
]
commands += [['node', '--check', str(p.relative_to(root))]
             for pattern in ('runtime/*.cjs', 'deploy/*.cjs', 'tools/*auth*.cjs')
             for p in sorted(root.glob(pattern))]
results = []
passed = True
for command in commands:
    start = time.perf_counter()
    completed = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=120)
    results.append({'command':[str(v).replace(sys.executable, 'python3') for v in command],
                    'exit_code':completed.returncode,
                    'elapsed_ms':round((time.perf_counter()-start)*1000, 2),
                    'output':completed.stdout+completed.stderr})
    print('PASS' if completed.returncode == 0 else 'FAIL', ' '.join(results[-1]['command']), flush=True)
    if completed.returncode:
        passed = False
        break
report = {'passed':passed, 'utc':datetime.now(timezone.utc).isoformat(),
          'environment':{'python':platform.python_version(), 'platform':platform.platform(),
                         'node':subprocess.check_output(['node', '--version'], text=True).strip(),
                         **{name:importlib.metadata.version(name) for name in ('cryptography','mypy','ruff')}},
          'results':results, 'external_broker_orders':0, 'paid_model_calls':0,
          'source':'HARPOON_Cloud_247.zip; inferred target masivarecords-ship-it/HerpoonX',
          'python_type_scope':'Three listed modules, check-untyped-defs, imports followed silently; dynamic HTTP factory inheritance has one narrow mypy exclusion.',
          'static_analysis_scope':'Python undefined/unbound name rules F821/F822/F823 and Node syntax checks; not a full security audit.',
          'docker_build_executed':False, 'deployed':False,
          'inference_scope':'Synthetic provider Responses payloads; no verification of a real model, billing, TLS or broker account.'}
(root/'evidence/auth_verification.json').write_text(json.dumps(report, indent=2)+'\n')
raise SystemExit(0 if passed else 1)
