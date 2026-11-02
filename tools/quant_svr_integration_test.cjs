'use strict';

// End-to-end numerical integration only. Fixtures are generated locally;
// an OBSERVED label is deliberately forged in one guard test, not market data.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {execFile} = require('node:child_process');
const {promisify} = require('node:util');
const execute = promisify(execFile);
const bridge = require('../runtime/quant_bridge.cjs');

const app = path.resolve(__dirname, '..');
const python = process.env.HARPOON_QUANT_PYTHON || 'python3';
let directory, fixture, originalModelEnvironment;

test.before(async () => {
  directory = fs.mkdtempSync(path.join(os.tmpdir(), 'harpoon-svr-integration-'));
  originalModelEnvironment = process.env.HARPOON_QUANT_MODEL;
  delete process.env.HARPOON_QUANT_MODEL;
  const program = String.raw`
import copy, json, sys
from pathlib import Path
sys.path.insert(0, 'examples/svr')
from make_fixture import build_fixture
from harpoon_quant.calibration import fit
from harpoon_quant.core import Config, digest, predict

destination = Path(sys.argv[1])
fixture = build_fixture()
cfg = Config(**fixture['config'])
model = fit(fixture['data'], fixture['available_at'], cfg, estimator='svr')
if not model['models']['SYNTHSVR']['accepted']:
    raise AssertionError('Deterministic nonlinear software fixture was not accepted')
candidate = fixture['request']['candidates'][0]
prediction = predict(model, 'SYNTHSVR', candidate['features'], fixture['request']['asof'], cfg)

def seal(value):
    value['artifact_hash'] = digest({k: v for k, v in value.items() if k != 'artifact_hash'})
    return value

observed_label = copy.deepcopy(model)
observed_label['origin'] = 'OBSERVED'  # Deliberate provenance forgery in a guard test.
seal(observed_label)
forged_permission = copy.deepcopy(observed_label)
forged_permission['research_only'] = False
forged_permission['independent_financial_validation'] = True
seal(forged_permission)
corrupted = copy.deepcopy(model)
corrupted['models']['SYNTHSVR']['svr']['intercept'] += 0.1
wrong_horizon = copy.deepcopy(model)
wrong_horizon['horizon_hours'] = 12
seal(wrong_horizon)
for name, value in [
    ('model.synthetic.json', model),
    ('observed_label_guard.json', observed_label),
    ('forged_permission_guard.json', forged_permission),
    ('corrupted_guard.json', corrupted),
    ('wrong_horizon_guard.json', wrong_horizon),
]:
    (destination / name).write_text(json.dumps(value, allow_nan=False))
print(json.dumps({'request': fixture['request'], 'prediction': prediction,
                  'origin': 'SYNTHETIC_ENGINEERING_ONLY'}))
`;
  const {stdout} = await execute(python, ['-c', program, directory], {
    cwd: path.join(app, 'quant'), encoding: 'utf8', timeout: 30000,
    env: {...process.env, OPENBLAS_NUM_THREADS: '1', OMP_NUM_THREADS: '1', PYTHONDONTWRITEBYTECODE: '1'},
  });
  fixture = JSON.parse(stdout);
});

test.after(() => {
  if (directory) fs.rmSync(directory, {recursive: true, force: true});
  if (originalModelEnvironment === undefined) delete process.env.HARPOON_QUANT_MODEL;
  else process.env.HARPOON_QUANT_MODEL = originalModelEnvironment;
});

function worker(name, implementation = bridge) {
  return implementation.worker(fixture.request, {
    calibrationFile: path.join(directory, name), python, timeoutMs: 8000,
  });
}

test('real Python SVR predicts a scalar and participates in bounded shadow allocation', async () => {
  const result = await worker('model.synthetic.json');
  assert.equal(result.forecast_model_kind, 'SVR_RBF');
  assert.equal(result.research_only, true);
  assert.equal(result.execution_allowed, false);
  assert.equal(result.liveApproved, false);
  assert.equal(fixture.origin, 'SYNTHETIC_ENGINEERING_ONLY');
  assert.ok(fixture.prediction > 0.01 && fixture.prediction < 0.04);
  assert.ok(Math.abs(result.forecasts.SYNTHSVR - fixture.prediction) < 1e-12);
  assert.ok(result.selected.length > 0, JSON.stringify(result));
  assert.ok(result.selected.every(item => item.quantity > 0 && item.quantity <= 5));
  assert.ok(result.cash_committed_usd <= fixture.request.account.cash);
});

test('an OBSERVED label does not authorize an SVR order', async () => {
  const result = await worker('observed_label_guard.json');
  assert.equal(result.execution_allowed, false);
  assert.equal(result.research_only, true);
  assert.ok(result.selected.length > 0, JSON.stringify(result));
  assert.ok(Math.abs(result.forecasts.SYNTHSVR - fixture.prediction) < 1e-12);
});

test('resealed permission flags cannot promote the SVR out of shadow mode', async () => {
  const result = await worker('forged_permission_guard.json');
  assert.equal(result.execution_allowed, false);
  assert.equal(result.liveApproved, false);
});

test('the Python worker rejects an altered SVR artifact hash', async () => {
  const result = await worker('corrupted_guard.json');
  assert.equal(result.execution_allowed, false);
  assert.deepEqual(result.selected, []);
  assert.match(JSON.stringify(result), /INTEGRITY/);
});

test('an incompatible forecast horizon cannot reach an allocation', async () => {
  const result = await worker('wrong_horizon_guard.json');
  assert.equal(result.execution_allowed, false);
  assert.deepEqual(result.selected, []);
  assert.match(JSON.stringify(result), /HORIZON/);
});

test('SVR discovery leaves the universe unchanged and issues no screener request', async () => {
  let requests = 0;
  const engine = {
    cfg: {universe: [{symbol: 'HELD', book: 'equity'}], quant: {
      calibrationFile: path.join(directory, 'observed_label_guard.json'), discoveryLimit: 48,
    }},
    api: {request: async () => { requests++; throw Error('NETWORK_MUST_NOT_BE_USED'); }},
  };
  const result = await bridge.discover(engine);
  assert.equal(result.reason, 'SVR_RESEARCH_ONLY');
  assert.deepEqual(result.added, []);
  assert.deepEqual(engine.cfg.universe, [{symbol: 'HELD', book: 'equity'}]);
  assert.equal(requests, 0);
});

test('an isolated predictor source change invalidates both binding and inference', async () => {
  const isolated = path.join(directory, 'source-change');
  fs.mkdirSync(path.join(isolated, 'runtime'), {recursive: true});
  fs.mkdirSync(path.join(isolated, 'runtime30'), {recursive: true});
  fs.mkdirSync(path.join(isolated, 'quant'), {recursive: true});
  fs.copyFileSync(path.join(app, 'runtime/quant_bridge.cjs'), path.join(isolated, 'runtime/quant_bridge.cjs'));
  // Binding now also covers operational accounting and coordinator guards.
  // Copy the complete compiled source set, then alter only the predictor.
  fs.cpSync(path.join(app, 'runtime30'), path.join(isolated, 'runtime30'), {recursive: true});
  fs.cpSync(path.join(app, 'quant/harpoon_quant'), path.join(isolated, 'quant/harpoon_quant'), {
    recursive: true, filter: source => !source.includes('__pycache__'),
  });
  const isolatedBridge = require(path.join(isolated, 'runtime/quant_bridge.cjs'));
  const engine = {cfg: {
    expected_account_id: 'SYNTHETIC_TEST_ACCOUNT',
    quant: {calibrationFile: path.join(directory, 'model.synthetic.json')},
    universe: [], enabledPlugins: [], exit: {},
  }, state: {exitProfile: {}, plugins: []}};
  const before = isolatedBridge.binding(engine);
  assert.equal(before.execution_hash, bridge.binding(engine).execution_hash);
  fs.appendFileSync(path.join(isolated, 'quant/harpoon_quant/scalar_svr.py'), '\n# Synthetic integrity regression: isolated source alteration.\n');
  const after = isolatedBridge.binding(engine);
  assert.notEqual(after.execution_hash, before.execution_hash);
  assert.equal(after.forecast_hash, before.forecast_hash);
  const result = await worker('model.synthetic.json', isolatedBridge);
  assert.equal(result.execution_allowed, false);
  assert.deepEqual(result.selected, []);
  assert.match(JSON.stringify(result), /SVR_IMPLEMENTATION_CHANGED/);
});
