#!/usr/bin/env python3
"""Plot registered MODULATION10 development metrics; no economic execution.

Read the analyzer's metrics and Pareto flags without recomputing either.
The only numeric transformations are fractions to percent and log units to bp.
PNG/SVG outputs embed the input report SHA-256 and the exploration disclaimer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DISPLAY_CONTROLS = ("CASH", "M9_BEST", "CURRENT")
COLORS = {"candidate": "#8193A3", "pareto": "#087F8C", "infeasible": "#B74735",
          "CASH": "#252D36", "M9_BEST": "#6C4AA0", "CURRENT": "#B77A0D"}
DISCLAIMER = ("SINTÉTICO · EXPLORACIÓN. Ocho semillas por mundo y coste. "
              "No es validación final ni un óptimo demostrado.")


@dataclass(frozen=True)
class Point:
    policy_id: str
    label: str
    x_percent: float
    y_bp_per_day: float
    kind: str
    pareto: bool
    risk_feasible: bool


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_points(report_path: Path, protocol_path: Path,
                registration_path: Path) -> tuple[list[Point], dict[str, Any]]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    registration = json.loads(registration_path.read_text(encoding="utf-8"))
    if (report.get("schema") != "HARPOON_MODULATION10_DEVELOPMENT_1"
            or report.get("stage") != "development" or report.get("origin") != "SYNTHETIC"):
        raise ValueError("ONLY_SYNTHETIC_MODULATION10_DEVELOPMENT_REPORTS_ALLOWED")
    if (report["protocol_sha256"] != sha256(protocol_path)
            or report["registration_sha256"] != sha256(registration_path)
            or registration["protocol_sha256"] != sha256(protocol_path)):
        raise ValueError("REPORT_CONTRACT_IDENTITY_MISMATCH")
    seeds = protocol["stages"]["development"]["seeds"]
    if len(seeds) != 8 or len(set(seeds)) != 8:
        raise ValueError("FIGURE_REQUIRES_EIGHT_DEVELOPMENT_SEEDS")
    if (protocol["selection"]["positive_edge_worlds"] != ["TREND", "WEAK"]
            or set(protocol["generator"]["worlds"]) != {"TREND", "WEAK", "FALSE", "NULL", "GAP"}
            or set(protocol["scenarios"]) != {"NOMINAL", "STRESS"}):
        raise ValueError("FIGURE_AGGREGATION_CONTRACT_MISMATCH")
    ordered_ids = [v["id"] for v in protocol["variants"] if v["role"] == "candidate"]
    candidates = {row["id"]: row for row in report["candidates"]}
    controls = {row["id"]: row for row in report["controls_descriptive"]}
    if (len(ordered_ids) != 18 or len(set(ordered_ids)) != 18
            or len(report["candidates"]) != 18 or report["candidate_count"] != 18
            or set(candidates) != set(ordered_ids) or not set(DISPLAY_CONTROLS) <= set(controls)):
        raise ValueError("FIGURE_CANDIDATE_OR_CONTROL_COVERAGE_MISMATCH")
    points: list[Point] = []
    for index, policy_id in enumerate([*ordered_ids, *DISPLAY_CONTROLS]):
        candidate = index < len(ordered_ids)
        row = candidates[policy_id] if candidate else controls[policy_id]
        for world in protocol["generator"]["worlds"]:
            for scenario in protocol["scenarios"]:
                if report["groups"][f"{policy_id}:{world}:{scenario}"]["paths"] != 8:
                    raise ValueError("FIGURE_GROUP_SEED_COUNT_MISMATCH")
        x = float(row["p95_stress_drawdown"]) * 100.0
        y = float(row["mean_nominal_edge_daily_log"]) * 10000.0
        if not math.isfinite(x) or not math.isfinite(y) or x < 0:
            raise ValueError("NONFINITE_OR_NEGATIVE_DRAWDOWN_METRIC")
        if not isinstance(row["risk_feasible"], bool):
            raise ValueError("NONBOOLEAN_RISK_FEASIBILITY")
        pareto = row["pareto"] if candidate else False
        if not isinstance(pareto, bool) or (pareto and not row["risk_feasible"]):
            raise ValueError("INVALID_REGISTERED_PARETO_FLAG")
        kind = ("pareto" if pareto else "candidate" if row["risk_feasible"] else "infeasible") if candidate else policy_id
        points.append(Point(policy_id, f"{index + 1:02d}" if candidate else policy_id,
                            x, y, kind, pareto, row["risk_feasible"]))
    provenance = {
        "report_sha256": sha256(report_path),
        "protocol_sha256": sha256(protocol_path),
        "registration_sha256": sha256(registration_path),
        "script_sha256": sha256(Path(__file__).resolve()),
        "candidate_count": len(ordered_ids),
        "pareto_count": sum(point.pareto for point in points),
        "display_controls": list(DISPLAY_CONTROLS),
        "seeds_per_world_cost": 8,
        "x_source": "p95_stress_drawdown * 100; all five STRESS worlds",
        "y_source": "mean_nominal_edge_daily_log * 10000; TREND/WEAK NOMINAL",
        "pareto_flags_source": "report.json; not recomputed by plotter",
        "point_jitter": False,
        "economic_policy_executions": 0,
        "disclaimer": DISCLAIMER,
    }
    return points, provenance


def place_labels(fig: Any, ax: Any, points: list[Point]) -> None:
    """Place labels in screen space, preserving every original data coordinate."""
    from matplotlib.font_manager import FontProperties
    from matplotlib.transforms import Bbox

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    font = FontProperties(family="DejaVu Sans", size=9)
    scale = fig.dpi / 72.0
    axes_box = ax.get_window_extent(renderer).padded(-4)
    # Only annotations share a label when coordinates coincide to display
    # precision. Every individual marker is still plotted at its actual value.
    groups: dict[tuple[float, float], list[Point]] = {}
    for point in points:
        groups.setdefault((round(point.x_percent, 10), round(point.y_bp_per_day, 10)), []).append(point)
    ordered = sorted(groups.values(), key=lambda items: (
        0 if any(item.kind in DISPLAY_CONTROLS for item in items) else 1 if any(item.pareto for item in items) else 2,
        items[0].x_percent, items[0].y_bp_per_day))
    marker_boxes = []
    for point in points:
        x, y = ax.transData.transform((point.x_percent, point.y_bp_per_day))
        marker_boxes.append(Bbox.from_bounds(x - 5, y - 5, 10, 10))
    occupied = []

    def overlap_area(a: Any, b: Any) -> float:
        return max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0)) * max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))

    for items in ordered:
        anchor = items[0]
        label = " / ".join(item.label for item in items)
        width, height, _ = renderer.get_text_width_height_descent(label, font, ismath=False)
        height = max(height, 12.0 * scale)
        pixel_x, pixel_y = ax.transData.transform((anchor.x_percent, anchor.y_bp_per_day))
        best: tuple[float, float, float, str, Any] | None = None
        for radius in (11, 18, 27, 39, 54, 72, 94):
            for angle in (30, -30, 150, -150, 70, -70, 110, -110, 0, 180, 90, -90):
                dx = radius * math.cos(math.radians(angle))
                dy = radius * math.sin(math.radians(angle))
                align = "left" if dx >= 0 else "right"
                left = pixel_x + dx * scale - (width if align == "right" else 0.0)
                bottom = pixel_y + dy * scale - height / 2.0
                box = Bbox.from_bounds(left - 3, bottom - 2, width + 6, height + 4)
                outside = box.width * box.height - overlap_area(box, axes_box)
                collision = sum(overlap_area(box, other) for other in occupied)
                collision += sum(overlap_area(box, other) for other in marker_boxes)
                score = outside * 100.0 + collision * 20.0 + radius
                proposal = (score, dx, dy, align, box)
                if best is None or score < best[0]:
                    best = proposal
        if best is None:
            raise RuntimeError("NO_LABEL_LAYOUT")
        _, dx, dy, align, box = best
        occupied.append(box)
        color = COLORS[items[0].kind] if len({item.kind for item in items}) == 1 else "#25384A"
        ax.annotate(label, (anchor.x_percent, anchor.y_bp_per_day), xytext=(dx, dy),
                    textcoords="offset points", ha=align, va="center", fontsize=9,
                    color=color, fontweight="medium", zorder=8, annotation_clip=False,
                    bbox={"boxstyle": "round,pad=0.14", "facecolor": "white", "edgecolor": "none", "alpha": 0.9},
                    arrowprops={"arrowstyle": "-", "color": "#94A2AE", "linewidth": 0.65,
                                "shrinkA": 3, "shrinkB": 6})


def render(points: list[Point], provenance: dict[str, Any], output_dir: Path,
           overwrite: bool = False) -> dict[str, Any]:
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/harpoon_modulation10_matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import MaxNLocator, StrMethodFormatter

    outputs = {extension: output_dir / f"modulation10_frontier.{extension}" for extension in ("png", "svg")}
    if not overwrite and any(path.exists() for path in outputs.values()):
        raise FileExistsError("Figure already exists; use --overwrite for an intentional visual revision.")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5,
                         "svg.fonttype": "none", "svg.hashsalt": "HARPOON_MODULATION10_FRONTIER_1",
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.labelcolor": "#25384A", "text.color": "#25384A",
                         "axes.edgecolor": "#BBC5CE", "xtick.color": "#536677", "ytick.color": "#536677"})
    fig = plt.figure(figsize=(16, 9.6), dpi=120, facecolor="white")
    ax = fig.add_axes((0.075, 0.25, 0.55, 0.59))
    key_ax = fig.add_axes((0.67, 0.25, 0.315, 0.59))
    key_ax.axis("off")
    fig.text(0.075, 0.946, "SINTÉTICO · EXPLORACIÓN", fontsize=20, fontweight="bold", color="#17354B")
    fig.text(0.075, 0.905, "MODULATION10 · Retorno y drawdown de 18 candidatos", fontsize=14, color="#536677")
    fig.text(0.075, 0.866, "Preferencia descriptiva: mayor retorno y menor drawdown", fontsize=10.5, color="#536677")
    styles: dict[str, dict[str, Any]] = {
        "candidate": {"marker": "o", "s": 70, "facecolors": COLORS["candidate"], "edgecolors": "white", "linewidths": 0.8},
        "pareto": {"marker": "D", "s": 105, "facecolors": COLORS["pareto"], "edgecolors": "white", "linewidths": 0.9},
        "infeasible": {"marker": "X", "s": 90, "facecolors": COLORS["infeasible"], "edgecolors": "white", "linewidths": 0.7},
        "CASH": {"marker": "s", "s": 140, "facecolors": "none", "edgecolors": COLORS["CASH"], "linewidths": 1.9},
        "M9_BEST": {"marker": "D", "s": 160, "facecolors": "none", "edgecolors": COLORS["M9_BEST"], "linewidths": 1.9},
        "CURRENT": {"marker": "*", "s": 230, "facecolors": "#EABF68", "edgecolors": COLORS["CURRENT"], "linewidths": 1.1},
    }
    for kind in ("candidate", "infeasible", "pareto", *DISPLAY_CONTROLS):
        selected = [point for point in points if point.kind == kind]
        if selected:
            ax.scatter([point.x_percent for point in selected], [point.y_bp_per_day for point in selected],
                       **styles[kind], zorder=4 if kind in DISPLAY_CONTROLS else 3)
    xs, ys = [point.x_percent for point in points], [point.y_bp_per_day for point in points]
    x_span, y_span = max(max(xs) - min(xs), 0.1), max(max(ys) - min(ys), 0.1)
    ax.set_xlim(max(0.0, min(xs) - 0.18 * x_span), max(xs) + 0.18 * x_span)
    ax.set_ylim(min(ys) - 0.22 * y_span, max(ys) + 0.22 * y_span)
    if ax.get_ylim()[0] <= 0 <= ax.get_ylim()[1]:
        ax.axhline(0, color="#8C9AA5", linewidth=0.9, linestyle="--", zorder=1)
    ax.set_axisbelow(True)
    ax.grid(color="#E6EBEF", linewidth=0.8)
    ax.set_xlabel("P95 del drawdown en STRESS (%)\nCinco mundos · 40 trayectorias por política", labelpad=12)
    ax.set_ylabel("Media nominal de log-retorno diario\nTREND / WEAK (pb por día calendario)", labelpad=13)
    ax.xaxis.set_major_locator(MaxNLocator(6))
    ax.yaxis.set_major_locator(MaxNLocator(7))
    ax.xaxis.set_major_formatter(StrMethodFormatter("{x:.2f}"))
    ax.yaxis.set_major_formatter(StrMethodFormatter("{x:.3f}" if y_span < 0.1 else "{x:.2f}"))
    place_labels(fig, ax, points)

    key_ax.text(0, 1.0, "Clave de candidatos", fontsize=12.5, fontweight="bold", va="top")
    key_ax.text(0, 0.941, f"Pareto en esta muestra: {provenance['pareto_count']} de 18", fontsize=10.5, color=COLORS["pareto"], va="top")
    candidates = [point for point in points if point.kind not in DISPLAY_CONTROLS]
    for index, point in enumerate(candidates):
        key_ax.text(0.0, 0.875 - index * 0.044, point.label, fontsize=9.6,
                    fontweight="bold", color=COLORS[point.kind], va="center")
        key_ax.text(0.085, 0.875 - index * 0.044, point.policy_id, fontsize=8.8,
                    fontfamily="DejaVu Sans Mono", color=COLORS[point.kind], va="center")
    key_ax.text(0, 0.035, "Los controles no integran esta frontera de candidatos.", fontsize=9.2, color="#536677", va="center")

    legend_rows = [("candidate", "Cumple riesgo observado"), ("pareto", "Pareto empírico"),
                   ("CASH", "CASH"), ("M9_BEST", "M9_BEST"), ("CURRENT", "CURRENT")]
    if any(point.kind == "infeasible" for point in points):
        legend_rows.insert(1, ("infeasible", "Fuera del filtro de riesgo"))
    handles = [Line2D([], [], marker=styles[kind]["marker"], linestyle="none", markersize=8,
                      markerfacecolor="none" if kind in ("CASH", "M9_BEST") else styles[kind]["facecolors"],
                      markeredgecolor=COLORS[kind], label=label) for kind, label in legend_rows]
    fig.legend(handles=handles, loc="center left", bbox_to_anchor=(0.067, 0.14), ncol=3,
               frameon=False, fontsize=10, handletextpad=0.65, columnspacing=1.7, labelspacing=0.75)
    fig.text(0.075, 0.095, "Ocho semillas por mundo y coste · y: 16 trayectorias NOMINAL; x: 40 trayectorias STRESS.", fontsize=10, color="#536677")
    fig.text(0.075, 0.066, "Sin validación final ni óptimo demostrado. Pareto y métricas se leen del informe; puntos coincidentes comparten etiqueta, sin desplazar sus coordenadas.", fontsize=9.2, color="#536677")
    fig.text(0.075, 0.036, "Fuente: development_analysis/report.json · SHA-256 " + provenance["report_sha256"][:20] + "…", fontsize=8.5, color="#83919D")
    description = json.dumps(provenance, ensure_ascii=False, sort_keys=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(outputs["png"], dpi=200, facecolor="white", metadata={
        "Title": "SINTÉTICO · EXPLORACIÓN", "Description": description, "Software": "HARPOONX MODULATION10 plotter"})
    fig.savefig(outputs["svg"], facecolor="white", metadata={
        "Title": "SINTÉTICO · EXPLORACIÓN", "Description": description, "Creator": "HARPOONX MODULATION10 plotter", "Date": None})
    plt.close(fig)
    return {"outputs": {extension: {"path": str(path.resolve()), "sha256": sha256(path)} for extension, path in outputs.items()},
            "input_report_sha256": provenance["report_sha256"], "plotted_candidates": len(candidates),
            "pareto_candidates": provenance["pareto_count"], "economic_policy_executions": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "evidence/modulation10/development_analysis/report.json")
    parser.add_argument("--protocol", type=Path, default=ROOT / "research/modulation10/protocol.json")
    parser.add_argument("--registration", type=Path, default=ROOT / "research/modulation10/registration.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evidence/modulation10/figures")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing generated figures only.")
    args = parser.parse_args()
    if not args.report.is_file():
        parser.error(f"Development report not available: {args.report}; no analysis or economic execution was started.")
    points, provenance = load_points(args.report, args.protocol, args.registration)
    result = render(points, provenance, args.output_dir, args.overwrite)
    if sha256(args.report) != provenance["report_sha256"]:
        raise RuntimeError("INPUT_REPORT_CHANGED_DURING_RENDER")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
