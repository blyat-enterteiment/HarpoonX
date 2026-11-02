# Migration validation

Source: HARPOON_XXXUltimate_30_18_0_Integral.zip, Library version 21.

- Archive SHA-256: `7668e206301a23b24ecb4e7f2200510f774cdacd53f854963686d22c848984c1`.
- Imported source commit: `3d816c055422d4981ab5f87133119fa17c102bac`.
- GitHub Actions import: https://github.com/blyat-enterteiment/HarpoonX/actions/runs/41394819787 — success.
- ZIP CRC passed; all 2,924 original manifest entries matched SHA-256.
- All 2,926 original archive files matched the remote Git blob hashes, with no missing or changed source files. The recursive remote tree was not truncated.
- Additional migration workflow, importer, provenance note and per-file receipt are separate from original source.

## Executed locally against the imported source

Environment: Linux, Node.js 24.22.1, Python 3.12.14. Dependencies installed using `npm ci --ignore-scripts`.

| Command | Result |
| --- | --- |
| `npm run typecheck:xxx` | Passed |
| `npm test` | Passed, 39 checks across five existing groups |
| `npm run test:ultimate` | 30 passed, 0 failed |
| `node --test tools/quant8_core_regression_test.cjs` | 4 passed, 0 failed |
| `PYTHONPATH=quant python3 -m unittest discover -s quant/tests` | 483 passed, 49.729 seconds |

The initial broader run before installing npm dependencies could not load `ws`; the reported successful runs above were executed after installation. These are migration checks, not independent model validation, market-performance certification, deployment verification or a profitability claim. No broker execution was enabled by the migration. Original application version 30.17.0 and research extension 30.18.0 were preserved; start with `EMPEZAR_30_18.md`.
