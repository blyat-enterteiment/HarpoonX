"""Run the release checks once; never connect to a trading account or a model."""
from pathlib import Path
import json, os, subprocess, time

root = Path(__file__).resolve().parents[1]
commands = [
    ['npm', 'test'], ['npm', 'run', 'test:auth'],
    ['npm', 'run', 'test:service'], ['npm', 'run', 'test:xxv'],
    ['npm', 'run', 'test:agents'], ['npm', 'run', 'test:profit'],
    ['npm', 'run', 'test:options'], ['npm', 'run', 'test:warroom'],
    ['npm', 'run', 'test:warroom:cloud'], ['npm', 'run', 'test:optimizer'], ['npm', 'run', 'test:autonomy'], ['node', 'tools/agents25_cloud.cjs'],
    ['node', 'tools/agents25_browser.cjs'], ['node', 'tools/warroom3_browser.cjs'],
    ['node', 'tools/warroom3_panel_browser.cjs'], ['node', 'tools/optimizer3_browser.cjs'], ['node', 'tools/autonomy3_browser.cjs'], ['node', 'tools/warroom3_load.cjs'],
]
tsc = Path(os.environ.get('HARPOON_QA_TSC', root / 'node_modules/typescript/bin/tsc'))
type_flags = ['--allowJs', '--checkJs', '--noEmit', '--skipLibCheck', '--target', 'ES2022', '--module', 'node16', '--types', 'node']
if os.environ.get('HARPOON_QA_TYPE_ROOTS'):
    type_flags += ['--typeRoots', os.environ['HARPOON_QA_TYPE_ROOTS']]
commands += [
    ['node', str(tsc), *type_flags, 'runtime/control.cjs', 'deploy/managed.cjs'],
    ['node', str(tsc), *type_flags, 'src/agents25.js', 'src/profit25.js', 'src/vector25.js'],
]
subprocess.run(['python3', 'xxv/build.py'], cwd=root, check=True)
results = []
for command in commands:
    start = time.perf_counter()
    process = subprocess.run(command, cwd=root, text=True, capture_output=True)
    record = dict(command=command, exit_code=process.returncode,
                  elapsed_ms=round((time.perf_counter()-start)*1000),
                  output=process.stdout+process.stderr)
    results.append(record)
    print(json.dumps(dict(check=' '.join(command[:3]), exit_code=process.returncode)), flush=True)
    if process.returncode:
        (root/'evidence/release25_3-failed.json').write_text(json.dumps(results, indent=2))
        raise SystemExit(record['output'])
syntax = 0
for pattern in ['src/**/*.js', 'runtime/*.cjs', 'deploy/*.cjs', 'xxv/*.js', 'tools/*3*.cjs']:
    for file in root.glob(pattern):
        subprocess.run(['node', '--check', str(file)], check=True, capture_output=True)
        syntax += 1
report = dict(version='25.3.2', commands=results, passed_commands=len(results), syntax_files=syntax,
              broker_orders_sent=0, paid_model_calls=0, deployed=False,
              financial_performance_validated=False,
              scope='Functional, failure, persistence, controller, browser, load and existing type checks. Broker inputs in tests are fixtures; separate Alpaca connector entitlement smoke test is read-only.')
(root/'evidence/release25_3-verification.json').write_text(json.dumps(report, indent=2, ensure_ascii=False))
print(json.dumps({k: report[k] for k in ['version','passed_commands','syntax_files','broker_orders_sent','paid_model_calls','financial_performance_validated']}))
