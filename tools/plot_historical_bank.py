#!/usr/bin/env python3
"""Plot frozen historical reports; no fit, replay, annualization or smoothing."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'harpoon_matplotlib_cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, MultipleLocator

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ('NOMINAL', 'STRESS')
POLICIES = ('C0', 'RIDGE', 'SVR')
INITIAL = 20000.0
VALIDATION_START = dt.datetime(2023, 7, 3)
VALIDATION_END = dt.datetime(2023, 12, 29)
TEST_START = dt.datetime(2024, 1, 2)
TEST_END = dt.datetime(2024, 8, 30)
COLORS = {'C0': '#424B54', 'RIDGE': '#0072B2', 'SVR': '#C64E20', 'CASH': '#188265'}
STYLES = {'C0': '-', 'RIDGE': '-', 'SVR': (0, (5, 2, 1, 2)), 'CASH': (0, (4, 3))}
LABELS = {'C0': 'C0 histórico', 'RIDGE': 'Ridge', 'SVR': 'SVR', 'CASH': 'Cash · sólo costes'}


def require(condition: bool, detail: str) -> None:
    if not condition:
        raise ValueError(detail)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number_es(value: float, digits: int = 0) -> str:
    return f'{value:,.{digits}f}'.replace(',', '_').replace('.', ',').replace('_', '.')


def load_curves(run_dir: Path) -> tuple:
    run_dir = run_dir.resolve()
    reports_path = run_dir / 'reports.json'
    mapping = json.loads(reports_path.read_text())
    require(set(mapping) == {f'{s}:{p}' for s in SCENARIOS for p in POLICIES}, 'Unexpected report mapping.')
    sources = [{'name': 'reports.json', 'sha256': digest(reports_path)}]
    all_dates, data, manifest_curves = None, {}, []
    for scenario in SCENARIOS:
        data[scenario] = {}
        daily_cost = 1 if scenario == 'NOMINAL' else 2
        for policy in POLICIES:
            filename = mapping[f'{scenario}:{policy}']
            path = (run_dir / filename).resolve()
            require(path.is_relative_to(run_dir), 'Report path escapes run directory.')
            report = json.loads(path.read_text())
            require(report['origin'] == 'HISTORICAL' and report['execution'] == 'MODELED_OHLCV', 'Unexpected report nature.')
            require(report['policy'] == policy and report['scenario'] == scenario, 'Report identity mismatch.')
            require(report['metadata']['continuous'] is True, 'Continuous equity required.')
            curve = report['curve']
            dates = [dt.datetime.strptime(r['session_id'], '%Y-%m-%d') for r in curve]
            require(len(curve) == 294 and len(set(dates)) == 294 and dates == sorted(dates), 'Expected 294 ordered sessions.')
            require(dates[0] == VALIDATION_START and dates[125] == VALIDATION_END
                    and dates[126] == TEST_START and dates[-1] == TEST_END, 'Phase boundaries differ.')
            if all_dates is None:
                all_dates = dates
            require(dates == all_dates, 'All curves must use the same sessions.')
            require(curve[0]['equity_start_usd'] == INITIAL, 'Initial capital differs.')
            for i, row in enumerate(curve):
                require(all(isinstance(row[k], (float, int)) and not isinstance(row[k], bool)
                            and math.isfinite(row[k]) for k in ('equity_start_usd', 'equity_end_usd', 'external_costs_usd')),
                        'Non-finite or invalid equity/cost.')
                require(row['external_costs_usd'] == daily_cost, 'Cash benchmark cost is not supported by source.')
                if i:
                    require(math.isclose(row['equity_start_usd'], curve[i-1]['equity_end_usd'], abs_tol=1e-8, rel_tol=0),
                            'Capital discontinuity; no reset may be hidden.')
            values = [r['equity_end_usd'] for r in curve]
            data[scenario][policy] = values
            sources.append({'name': filename, 'sha256': digest(path)})
            manifest_curves.append({'scenario': scenario, 'policy': policy, 'source': filename,
                'source_field': 'curve[].equity_end_usd', 'session_field': 'curve[].session_id',
                'points': len(values), 'initial_equity_usd': curve[0]['equity_start_usd'],
                'final_equity_usd_original_precision': values[-1],
                'final_equity_label_six_decimals': number_es(values[-1], 6)})
        cash = [INITIAL - daily_cost * (i + 1) for i in range(len(all_dates))]
        data[scenario]['CASH'] = cash
        manifest_curves.append({'scenario': scenario, 'policy': 'CASH', 'nature': 'DERIVED_DESCRIPTIVE_COST_REFERENCE',
            'formula': '20000 - cost_per_session_usd * completed_session_count',
            'cost_per_session_usd': daily_cost, 'points': len(cash),
            'final_equity_usd_original_precision': cash[-1],
            'final_equity_label_six_decimals': number_es(cash[-1], 6),
            'assumed_interest_and_trading_pnl_usd': 0})
    return all_dates, data, sources, manifest_curves


def plot(run_dir: Path, output_dir: Path) -> dict:
    dates, curves, sources, manifest_curves = load_curves(run_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
        'axes.spines.top': False, 'axes.spines.right': False, 'axes.edgecolor': '#A5ACB4',
        'axes.linewidth': 0.8, 'svg.hashsalt': 'HARPOON_HISTORICAL_EQUITY_30_16_0',
        'savefig.facecolor': 'white'})
    fig = plt.figure(figsize=(15, 10.5), facecolor='white')
    layout = fig.add_gridspec(2, 2, left=0.085, right=0.975, top=0.79, bottom=0.13,
                             width_ratios=[4.4, 1.55], hspace=0.48, wspace=0.16)
    values = [INITIAL] + [x for scenario in curves.values() for series in scenario.values() for x in series]
    lower = math.floor(min(values) / 100) * 100 - 40
    upper = math.ceil(max(values) / 100) * 100 + 40
    months = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
    ticks = [dt.datetime(2023, 7, 3), dt.datetime(2023, 9, 1), dt.datetime(2023, 11, 1),
             dt.datetime(2024, 1, 2), dt.datetime(2024, 3, 1), dt.datetime(2024, 5, 1), dt.datetime(2024, 7, 1), TEST_END]
    legend = [Line2D([], [], color=COLORS[p], linestyle=STYLES[p], lw=2.1, label=LABELS[p])
              for p in (*POLICIES, 'CASH')]
    fig.suptitle('HISTÓRICO · EJECUCIÓN MODELADA', x=0.085, y=0.965, ha='left',
                 fontsize=21, fontweight='bold', color='#17212B')
    fig.text(0.085, 0.924, 'AAPL · MSFT · SPY · XLK  |  Patrimonio continuo desde 20.000 USD',
             fontsize=12.5, color='#485260')
    fig.legend(handles=legend, loc='upper left', bbox_to_anchor=(0.078, 0.902),
               ncol=4, frameon=False, fontsize=11.5, columnspacing=2.25, handlelength=3.2)

    for index, scenario in enumerate(SCENARIOS):
        ax = fig.add_subplot(layout[index, 0])
        table = fig.add_subplot(layout[index, 1])
        table.set_axis_off()
        ax.axvspan(VALIDATION_START, TEST_START, color='#EDF0F4', zorder=0)
        ax.axvspan(TEST_START, TEST_END, color='#F5F8FB', zorder=0)
        ax.axvline(TEST_START, color='#657381', linewidth=1.0, linestyle=(0, (3, 3)), zorder=2)
        for policy in ('CASH', *POLICIES):
            # The duplicate initial date draws the opening capital before that
            # first session's closing value; no artificial extra session is added.
            x = [dates[0], *dates]
            y = [INITIAL, *curves[scenario][policy]]
            ax.plot(x, y, color=COLORS[policy], linestyle=STYLES[policy],
                    linewidth=1.85 if policy != 'CASH' else 1.6, alpha=0.97, zorder=4)
        ax.set_ylim(lower, upper)
        ax.set_xlim(VALIDATION_START - dt.timedelta(days=4), TEST_END + dt.timedelta(days=6))
        ax.yaxis.set_major_locator(MultipleLocator(250))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: number_es(value)))
        ax.set_xticks(ticks)
        ax.set_xticklabels([f'{months[x.month-1]}\n{x.year}' for x in ticks], fontsize=10)
        ax.grid(axis='y', color='#D8DEE5', linewidth=0.65, alpha=0.9)
        ax.set_ylabel('Patrimonio (USD)', labelpad=11)
        ax.tick_params(axis='both', length=3.5, color='#A5ACB4')
        scenario_name = 'NOMINAL' if scenario == 'NOMINAL' else 'ESTRÉS'
        cost = 1 if scenario == 'NOMINAL' else 2
        ax.set_title(f'{scenario_name}  ·  Coste externo: {cost} USD por sesión', loc='left',
                     pad=34, fontsize=13, fontweight='bold', color='#17212B')
        transform = ax.get_xaxis_transform()
        ax.text(VALIDATION_START + (TEST_START-VALIDATION_START)/2, 1.025,
                'VALIDACIÓN · 03 jul–29 dic 2023', transform=transform,
                ha='center', va='bottom', fontsize=9.4, color='#566475')
        ax.text(TEST_START + (TEST_END-TEST_START)/2, 1.025,
                'PRUEBA · 02 ene–30 ago 2024', transform=transform,
                ha='center', va='bottom', fontsize=9.4, color='#566475')
        table.text(0, 0.985, 'PATRIMONIO FINAL (USD)', fontsize=10.5, fontweight='bold', color='#17212B', va='top')
        table.text(0, 0.895, '30 de agosto de 2024', fontsize=10, color='#667383', va='top')
        for i, policy in enumerate((*POLICIES, 'CASH')):
            y = 0.73 - i * 0.18
            table.plot([0.0, 0.10], [y, y], color=COLORS[policy], linestyle=STYLES[policy], lw=2,
                       transform=table.transAxes, clip_on=False)
            table.text(0.14, y, LABELS[policy], transform=table.transAxes, fontsize=10.5,
                       color=COLORS[policy], va='center')
            table.text(0.14, y - 0.075, number_es(curves[scenario][policy][-1], 6),
                       transform=table.transAxes, fontsize=12, fontweight='bold', color='#17212B', va='center')
        table.set_xlim(0, 1)
        table.set_ylim(0, 1)

    fig.text(0.085, 0.079, '294 cierres de sesión · misma escala USD · capital acumulado sin reinicio entre validación y prueba.',
             fontsize=10, color='#45515F')
    fig.text(0.085, 0.054, 'Cash = 20.000 USD menos costes por sesión; referencia sin operaciones ni intereses. Trazos sin suavizado ni proyección.',
             fontsize=9.7, color='#45515F')
    fig.text(0.085, 0.031, 'Saldos mostrados con seis decimales; precisión original y hashes de entrada conservados en el manifiesto del gráfico.',
             fontsize=9.2, color='#667383')
    png, svg = output_dir / 'curvas_patrimonio.png', output_dir / 'curvas_patrimonio.svg'
    fig.savefig(png, dpi=180, metadata={'Software': 'HarpoonX plot_historical_bank.py / Matplotlib'})
    fig.savefig(svg, metadata={'Date': None, 'Creator': 'HarpoonX plot_historical_bank.py / Matplotlib',
                              'Title': 'Histórico: ejecución modelada, patrimonio continuo'})
    plt.close(fig)
    for source in sources:
        require(digest(run_dir / source['name']) == source['sha256'], 'Input source changed during plotting.')
    manifest = {'schema': 'HARPOON_HISTORICAL_EQUITY_PLOT_1',
        'scope': 'DESCRIPTIVE_PLOT_OF_COMPLETED_FROZEN_RUN',
        'new_financial_variants': 0, 'model_training_or_replay_executed': False,
        'sources': sources, 'script_sha256': digest(Path(__file__)), 'matplotlib_version': matplotlib.__version__,
        'session_count': 294, 'validation_sessions': 126, 'test_sessions': 168,
        'common_y_limits_usd': [lower, upper], 'initial_capital_usd': INITIAL,
        'capital_reset_between_phases': False, 'annualization': False, 'smoothing': False, 'projection': False,
        'curves': manifest_curves,
        'outputs': [{'name': x.name, 'bytes': x.stat().st_size, 'sha256': digest(x)} for x in (png, svg)]}
    (output_dir / 'curvas_patrimonio_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, default=ROOT / 'evidence/historical_bank_30_16_0/run_completed')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'evidence/historical_bank_30_16_0/analysis')
    args = parser.parse_args()
    manifest = plot(args.run_dir.resolve(), args.output_dir.resolve())
    print(json.dumps({'outputs': manifest['outputs'], 'curves': manifest['curves']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
