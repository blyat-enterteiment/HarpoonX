"""HarpoonX: render measured Modulation9 evidence as an A4 Spanish PDF.

No simulation, fitting, strategy selection or source-tree mutation occurs here.
Default mode validates inputs only. Run the PDF skill marker exactly once,
immediately before the first invocation with --generate. This script never
runs that marker itself. A completed final report and framework are mandatory.
Dependencies: reportlab, matplotlib, numpy, Pillow and pypdf. Poppler is used
separately for visual review; --root and --output make paths portable.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
from PIL import Image as PILImage
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak,
)

SOURCE_DIR = Path(__file__).resolve().parent
ROOT = SOURCE_DIR.parent if SOURCE_DIR.name == "tools" and (SOURCE_DIR.parent / "runtime30").is_dir() else SOURCE_DIR / "HarpoonX"
BASE = ROOT.parent
DEFAULT_PDF = BASE / "output/pdf/HarpoonX_Modulacion9_Informe_20261107.pdf"
REPO = "https://github.com/blyat-enterteiment/HarpoonX"
BRANCH = "codex/synthetic-modulation9"
WORLDS = ("TREND", "WEAK", "FALSE", "NULL", "GAP")
SCENARIOS = ("NOMINAL", "STRESS")
CONTROLS = ("CURRENT", "SIMPLE", "CASH")
ENDPOINTS = ("ABSOLUTE", "CURRENT", "SIMPLE", "CASH")
NAVY = colors.HexColor("#142E43")
TEAL = colors.HexColor("#087F8C")
INK = colors.HexColor("#24394A")
GRAY = colors.HexColor("#627281")
PALE = colors.HexColor("#EDF4F7")
LINE = colors.HexColor("#D4E0E7")
RED = colors.HexColor("#A62A32")
GREEN = colors.HexColor("#176F59")
AMBER = colors.HexColor("#BA7417")
W = A4[0] - 36 * mm
STYLES: dict[str, ParagraphStyle] = {}

GATE_LABELS = {
    "complete_64_final_paths_per_world_cost": "Cobertura final completa: 64 semillas por mundo y coste.",
    "development_score_positive": "Score de desarrollo estrictamente positivo.",
    "nominal_edge_absolute_lower_above_1bp_daily": "TREND y WEAK nominales: cota inferior > 1 pb de log-crecimiento diario.",
    "stress_edge_absolute_lower_positive": "TREND y WEAK bajo estrés: cota inferior > 0.",
    "paired_edge_improvement_over_all_controls": "Mejora emparejada frente a CURRENT, SIMPLE y CASH en ambos mundos y costes.",
    "observed_risk_holding_and_reconciliation": "Riesgo observado, plazo, equity y conciliación dentro del contrato.",
    "tail_world_cost_relative_terminal_loss_within_half_pct": "NULL, FALSE y GAP: diferencia media frente a CASH >= -0,5 puntos porcentuales.",
    "null_has_no_positive_adjusted_absolute_or_cash_relative_lower": "NULL: ninguna cota inferior positiva, absoluta o frente a CASH.",
    "edge_profit_survives_removing_each_best_campaign": "Beneficio positivo tras restar la mejor campaña de cada cuenta en TREND/WEAK.",
    "complete_entry_partial_reject_outage_impact_model": "Modelo completo de parciales de entrada, rechazos, caídas e impacto.",
    "full_current_virtual_matrix_execution_integration": "Integración completa del coordinador de la matriz virtual.",
}


def number(value: float, places: int = 2, signed: bool = False) -> str:
    if not math.isfinite(float(value)):
        raise ValueError("NONFINITE_REPORT_NUMBER")
    spec = f"{float(value):{'+' if signed else ''},.{places}f}"
    return spec.replace(",", "_").replace(".", ",").replace("_", ".")


def pct(value: float, places: int = 2, signed: bool = False) -> str:
    return number(value * 100, places, signed) + "%"


def usd(value: float, signed: bool = False) -> str:
    return number(value, 2, signed) + " USD"


def bp(value: float, places: int = 3) -> str:
    return number(value * 10000, places)


def norm(text: Any) -> str:
    value = str(text)
    for char in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212"):
        value = value.replace(char, "-")
    return value.replace("\u00a0", " ")


def esc(text: Any) -> str:
    return html.escape(norm(text))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Required completed evidence is absent: {path}")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


@dataclass
class Evidence:
    root: Path
    development: dict[str, Any]
    final: dict[str, Any]
    protocol: dict[str, Any]
    registration: dict[str, Any]
    qa: dict[str, Any]
    framework: str
    files: dict[str, Path]
    legacy: dict[str, Any] | None
    baseline: dict[str, Any] | None
    independent: dict[str, Any] | None
    calendar_days: int

    @classmethod
    def load(cls, root: Path) -> "Evidence":
        files = {
            "D": root / "evidence/modulation9/development_analysis/report.json",
            "F": root / "evidence/modulation9/final_analysis/report.json",
            "P": root / "research/modulation9/protocol.json",
            "R": root / "research/modulation9/registration.json",
            "Q": root / "evidence/modulation9/qa/ci_static_and_types.json",
            "M": root / "docs/MODULATION9_FRAMEWORK.md",
        }
        dev, final, protocol, registration, qa = (read_json(files[k]) for k in ("D", "F", "P", "R", "Q"))
        framework = files["M"].read_text()
        if dev["stage"] != "development" or final["stage"] != "final" or final["origin"] != "SYNTHETIC":
            raise ValueError("REPORT_STAGE_OR_ORIGIN")
        if final["candidate_id"] != dev["selection"]["candidate_id"]:
            raise ValueError("REPORT_SELECTION_MISMATCH")
        if (final["protocol_sha256"] != sha(files["P"]) or
                final["protocol_sha256"] != registration["protocol_sha256"] or
                final["selection_sha256"] != dev["selection"]["selection_sha256"]):
            raise ValueError("REPORT_HASH_BINDING")
        if final["execution_allowed"] or final["real_profitability_accredited"] or final["level9_real_accredited"]:
            raise ValueError("REPORT_OFFLINE_SYNTHETIC_SCOPE")
        if len(dev["candidates"]) != 36 or len(final["endpoints"]) != 40:
            raise ValueError("REPORT_REGISTERED_MATRIX_SHAPE")
        policies = (final["candidate_id"], *CONTROLS)
        for policy in policies:
            for world in WORLDS:
                for scenario in SCENARIOS:
                    group = final["groups"][f"{policy}:{world}:{scenario}"]
                    for key in ("mean_net_usd", "mean_return", "p95_drawdown", "worst_drawdown", "mean_daily_log"):
                        if not math.isfinite(group[key]):
                            raise ValueError(f"REPORT_NONFINITE_GROUP:{key}")
                    if abs(group["mean_net_usd"] / protocol["limits"]["capitalUsd"] - group["mean_return"]) > 1e-10:
                        raise ValueError("REPORT_RETURN_UNIT")
        nominal_fixed = final["groups"]["CASH:TREND:NOMINAL"]["mean_fixed_cost_usd"]
        day_cost = protocol["scenarios"]["NOMINAL"]["external_cost_usd_per_calendar_day"]
        days = round(nominal_fixed / day_cost)
        for group_key, group in final["groups"].items():
            scenario = group_key.rsplit(":", 1)[1]
            if abs(group["mean_fixed_cost_usd"] - days * protocol["scenarios"][scenario]["external_cost_usd_per_calendar_day"]) > 1e-7:
                raise ValueError("REPORT_CALENDAR_COST_BINDING")
        legacy_paths = sorted((root / "evidence/modulation9").rglob("legacy_ci_diagnosis.json"))
        legacy = read_json(legacy_paths[0]) if legacy_paths else None
        if legacy_paths:
            files["L"] = legacy_paths[0]
        baseline_path = root / "evidence/modulation9/baseline/forensic_review.json"
        baseline = read_json(baseline_path) if baseline_path.exists() else None
        independent_path = root / "evidence/modulation9/qa/independent_review.json"
        independent = read_json(independent_path) if independent_path.exists() else None
        if independent:
            files["I"] = independent_path
            if independent["binding"]["final_report_sha256"] != sha(files["F"]):
                raise ValueError("INDEPENDENT_REVIEW_REPORT_BINDING")
        results_path = root / "docs/MODULATION9_RESULTS.md"
        if results_path.exists():
            files["S"] = results_path
        return cls(root, dev, final, protocol, registration, qa, framework, files, legacy, baseline, independent, days)

    @property
    def selected(self) -> str:
        return self.final["candidate_id"]

    def group(self, world: str, scenario: str, policy: str | None = None, stage: str = "final") -> dict[str, Any]:
        source = self.final if stage == "final" else self.development
        return source["groups"][f"{policy or self.selected}:{world}:{scenario}"]

    def candidate_groups(self) -> list[dict[str, Any]]:
        return [self.group(w, s) for w in WORLDS for s in SCENARIOS]

    def control_score(self, control: str) -> float:
        groups = [self.group(w, s, control, "development") for w in ("TREND", "WEAK") for s in SCENARIOS]
        return min(g["mean_daily_log"] - 1.645 * g["standard_error_daily_log"] for g in groups)


def setup_fonts() -> None:
    directory = Path("/usr/share/fonts/truetype/dejavu")
    if not (directory / "DejaVuSans.ttf").exists():
        directory = Path(matplotlib.get_data_path()) / "fonts/ttf"
    for name, file in (("HX", "DejaVuSans.ttf"), ("HX-Bold", "DejaVuSans-Bold.ttf"),
                       ("HX-Italic", "DejaVuSans-Oblique.ttf"), ("HX-Mono", "DejaVuSansMono.ttf")):
        pdfmetrics.registerFont(TTFont(name, str(directory / file)))
    pdfmetrics.registerFontFamily("HX", normal="HX", bold="HX-Bold", italic="HX-Italic", boldItalic="HX-Bold")
    basic = dict(fontName="HX", textColor=INK, spaceAfter=7, allowWidows=0, allowOrphans=0)
    STYLES.update({
        "body": ParagraphStyle("body", fontSize=9.2, leading=13.1, **basic),
        "small": ParagraphStyle("small", fontSize=8.0, leading=11.1, **basic),
        "tiny": ParagraphStyle("tiny", fontSize=7.2, leading=9.8, **basic),
        "note": ParagraphStyle("note", fontSize=8.0, leading=11.4, textColor=GRAY,
                               fontName="HX", spaceAfter=8),
        "h1": ParagraphStyle("h1", fontName="HX-Bold", fontSize=20, leading=25,
                             textColor=NAVY, spaceAfter=12, keepWithNext=True),
        "h2": ParagraphStyle("h2", fontName="HX-Bold", fontSize=11.3, leading=15.5,
                             textColor=TEAL, spaceBefore=9, spaceAfter=6, keepWithNext=True),
        "cover": ParagraphStyle("cover", fontName="HX-Bold", fontSize=38, leading=43,
                                textColor=NAVY, spaceAfter=12),
        "subtitle": ParagraphStyle("subtitle", fontName="HX", fontSize=17, leading=23,
                                   textColor=TEAL, spaceAfter=14),
        "white": ParagraphStyle("white", fontName="HX", fontSize=9.1, leading=13.4,
                                textColor=colors.white, spaceAfter=2),
        "thead": ParagraphStyle("thead", fontName="HX-Bold", fontSize=8.1, leading=11.2,
                                textColor=colors.white, spaceAfter=0),
        "cell": ParagraphStyle("cell", fontName="HX", fontSize=8.1, leading=11.1,
                               textColor=INK, spaceAfter=0),
        "cellsmall": ParagraphStyle("cellsmall", fontName="HX", fontSize=7.5, leading=10.1,
                                    textColor=INK, spaceAfter=0),
        "mono": ParagraphStyle("mono", fontName="HX-Mono", fontSize=7.0, leading=9.6,
                               textColor=INK, spaceAfter=0),
    })


def p(text: Any, style: str = "body", markup: bool = False) -> Paragraph:
    return Paragraph(norm(text) if markup else esc(text), STYLES[style])


def h(text: str) -> Paragraph:
    return p(text, "h2")


def title(number_: str, text: str) -> list[Any]:
    return [p(f"{number_} / {text}", "h1")]


def table(headers: list[str], rows: list[list[Any]], widths: list[float] | None = None,
          small: bool = False, highlights: set[int] | None = None) -> Table:
    style = "cellsmall" if small else "cell"
    data = [[p(x, "thead") for x in headers]]
    data += [[x if isinstance(x, Paragraph) else p(x, style) for x in row] for row in rows]
    t = Table(data, colWidths=widths or [W / len(headers)] * len(headers), repeatRows=1, hAlign="LEFT")
    commands: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, 0), .7, NAVY),
        ("LINEBELOW", (0, 1), (-1, -1), .35, LINE),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            commands.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F5F8FA")))
        if highlights and i - 1 in highlights:
            commands.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FFF1D9")))
    t.setStyle(TableStyle(commands))
    return t


def box(heading: str, text: str, color: colors.Color = PALE) -> Table:
    t = Table([[p(heading, "h2")], [p(text, "body")]], colWidths=[W], hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), color),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, 0), 4), ("BOTTOMPADDING", (0, -1), (-1, -1), 10)]))
    return t


def plot_image(path: Path, max_height: float) -> Image:
    with PILImage.open(path) as im:
        width, height = im.size
    scale = min(W / width, max_height / height)
    return Image(str(path), width=width * scale, height=height * scale, hAlign="CENTER")


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.states: list[dict[str, Any]] = []

    def showPage(self) -> None:
        self.states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        count = len(self.states)
        for state in self.states:
            self.__dict__.update(state)
            self.setStrokeColor(LINE)
            self.setLineWidth(.5)
            self.line(18 * mm, 15 * mm, A4[0] - 18 * mm, 15 * mm)
            self.setFont("HX", 7)
            self.setFillColor(GRAY)
            self.drawString(18 * mm, 10.8 * mm, "HARPOONX  |  07 NOV 2026  |  INVESTIGACION SINTETICA")
            self.drawRightString(A4[0] - 18 * mm, 10.8 * mm, f"{self._pageNumber} / {count}")
            super().showPage()
        super().save()


def page_header(canv: canvas.Canvas, doc: SimpleDocTemplate) -> None:
    if doc.page == 1:
        return
    canv.saveState()
    canv.setFillColor(TEAL)
    canv.setFont("HX-Bold", 7.5)
    canv.drawString(18 * mm, A4[1] - 12 * mm, "HARPOONX / MODULACION 9")
    canv.setFillColor(GRAY)
    canv.setFont("HX", 7.1)
    canv.drawRightString(A4[0] - 18 * mm, A4[1] - 12 * mm, "Evidencia, limites y decision")
    canv.restoreState()


def create_charts(e: Evidence, directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.labelcolor": "#24394A", "text.color": "#24394A",
                         "axes.titleweight": "bold", "figure.facecolor": "white", "savefig.facecolor": "white"})
    palette = {"CONFIRMED": "#436C9B", "QUALITY": "#087F8C", "RETEST": "#A470C1"}
    fig, ax = plt.subplots(figsize=(8.1, 5.0))
    for entry in palette:
        items = [r for r in e.development["candidates"] if r["entry"] == entry]
        ax.scatter([r["p95_stress_drawdown"] * 100 for r in items],
                   [r["mean_nominal_edge_daily_log"] * 1e4 for r in items],
                   s=[38 + 85 * r["risk"] / .0025 for r in items], c=palette[entry],
                   alpha=.8, edgecolor="white", linewidth=.7, label=entry, zorder=3)
        bad = [r for r in items if not r["risk_feasible"]]
        if bad:
            ax.scatter([r["p95_stress_drawdown"] * 100 for r in bad],
                       [r["mean_nominal_edge_daily_log"] * 1e4 for r in bad], marker="x", c="#A62A32", s=130)
    frontier = sorted([r for r in e.development["candidates"] if r["pareto"]], key=lambda r: r["p95_stress_drawdown"])
    if frontier:
        ax.plot([r["p95_stress_drawdown"] * 100 for r in frontier],
                [r["mean_nominal_edge_daily_log"] * 1e4 for r in frontier], "--", color="#627281", linewidth=1.2,
                label="Pareto factible", zorder=2)
    c = e.final["candidate"]
    x, y = c["p95_stress_drawdown"] * 100, c["mean_nominal_edge_daily_log"] * 1e4
    ax.scatter([x], [y], s=260, facecolors="none", edgecolors="#BA7417", linewidth=2.5, zorder=5)
    ax.annotate("Seleccion bloqueada\n" + e.selected, xy=(x, y), xytext=(.24, .65),
                textcoords="axes fraction", fontsize=9, color="#7F510E",
                bbox={"facecolor": "#FFF1D9", "edgecolor": "#E5C28F", "boxstyle": "round,pad=.45"},
                arrowprops={"arrowstyle": "-", "color": "#BA7417"})
    ax.axhline(0, color="#A62A32", linewidth=1, linestyle=":", label="Crecimiento neto cero")
    ax.set_xlabel("DD p95 bajo STRESS, cinco mundos (%)")
    ax.set_ylabel("Log-crecimiento nominal diario medio\nTREND + WEAK (pb por dia calendario)")
    ax.grid(alpha=.18, zorder=0)
    ax.legend(loc="upper center", bbox_to_anchor=(.5, 1.18), fontsize=8.4, ncol=3, frameon=False)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: number(v, 1)))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: number(v, 2)))
    fig.tight_layout(pad=1.1)
    frontier_path = directory / "frontera_36_modulaciones.png"
    fig.savefig(frontier_path, dpi=200)
    plt.close(fig)

    colors_ = ("#087F8C", "#436C9B", "#8697A5", "#C4CBD1")
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.8), sharey=True)
    for ax, scenario in zip(axes, SCENARIOS):
        for j, (policy, color) in enumerate(zip((e.selected, *CONTROLS), colors_)):
            values = [e.group(w, scenario, policy)["mean_return"] * 100 for w in WORLDS]
            ax.barh(np.arange(5) + (j - 1.5) * .18, values, height=.16, color=color,
                    label="Seleccionada" if j == 0 else policy)
        ax.set_yticks(range(5), WORLDS)
        ax.axvline(0, color="#627281", linewidth=.7)
        ax.set_title(scenario, fontsize=11)
        ax.set_xlabel("Rentabilidad neta media (%)", fontsize=9.4)
        ax.grid(axis="x", alpha=.15)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: number(v, 1)))
    axes[0].invert_yaxis()
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False, fontsize=9)
    fig.tight_layout(rect=(0, .10, 1, 1))
    final_path = directory / "comparacion_final_5_mundos.png"
    fig.savefig(final_path, dpi=200)
    plt.close(fig)
    return {"frontier": frontier_path, "final": final_path}


def cover(e: Evidence) -> list[Any]:
    f, c = e.final, e.final["candidate"]
    groups = e.candidate_groups()
    edge = [e.group(w, s) for w in ("TREND", "WEAK") for s in SCENARIOS]
    positives = sum(g["mean_net_usd"] > 0 for key, g in e.development["groups"].items()
                    if key.split(":", 1)[0] not in CONTROLS)
    economic_text = ("Cumple los criterios económicos dentro del modelo registrado."
                     if f["economic_model_feasibility"] else "No cumple los criterios económicos del modelo registrado.")
    operational_text = (f"Faltan {len(f['framework_missing_before_measurement'])} componentes operativos declarados antes de medir. "
                        "No existe acreditación de rentabilidad real ni autorización de órdenes.")
    out = [Spacer(1, 12 * mm), p("HarpoonX", "cover"),
           p("Modulación 9", "subtitle"),
           p("Análisis forense, riesgo y rentabilidad en un banco de pruebas sintético", "h1"),
           p("Informe de resultados y framework de trabajo · 7 de noviembre de 2026", "note"), Spacer(1, 7 * mm),
           box("DICTAMEN ECONÓMICO / " + f["verdict"], economic_text + " " +
               f"Fallan {len(f['economic_failed_gates'])} puertas económicas de las predefinidas.", colors.HexColor("#FBEFF0")),
           Spacer(1, 5 * mm), box("ESTADO DEL FRAMEWORK", operational_text), Spacer(1, 6 * mm),
           h("Receta seleccionada para contraste"), p(e.selected, "h2"),
           p(f"Entrada {c['entry']} · salida {c['exit']} · riesgo por campaña {pct(c['risk'], 4)}. "
             "La selección pertenece a una cuadrícula finita; no acredita un óptimo global."),
           table(["Exploración", "Validación final", "Horizonte por cuenta"], [[
               f"36 modulaciones + 3 controles\n{number(e.development['account_count'], 0)} cuentas",
               f"{f['statistics']['independent_seeds']} semillas por mundo\n{number(f['account_count'], 0)} cuentas",
               f"{e.protocol['generator']['evaluation_sessions']} sesiones\n{e.calendar_days} días de calendario"]]),
           Spacer(1, 5 * mm),
           p(f"En desarrollo, {positives} de {36 * 5 * 2} medias netas por receta, mundo y coste fueron positivas. "
             f"En el final, el retorno medio de la seleccionada en TREND/WEAK va de "
             f"{pct(min(g['mean_return'] for g in edge), 3)} a {pct(max(g['mean_return'] for g in edge), 3)}. "
             f"Su peor drawdown observado es {pct(max(g['worst_drawdown'] for g in groups), 3)}."),
           p("Todas las cifras son sintéticas, netas de los costes registrados y sin anualizar. "
             "Fuentes: desarrollo [D], final independiente [F], protocolo [P] y framework [M].", "note")]
    return out


def design(e: Evidence) -> list[Any]:
    p_ = e.protocol
    entries = [
        ["CONFIRMED", "Dos cierres sobre el máximo de los primeros 30 min, retorno relativo positivo y RVOL > 1. Decisión a 60 min + 1 s; siguiente apertura de 5 min."],
        ["QUALITY", "CONFIRMED más RVOL <= 3, extensión <= 0,6 ATR previo, retorno previo de 30 días y MACD diario positivos. EMA sobre 50 cierres previos."],
        ["RETEST", "Decisión a 90 min + 1 s tras ruptura y revisita a la banda de 0,15 ATR; dos cierres sobre el nivel, RVOL 0,8-3 y tendencia previa positiva."],
    ]
    exits = [
        ["NATIVE72", "25% a 1,5R y 25% a 3R; trailing nativo. Máximo 72 h. Conserva la conducta de recepción heredada."],
        ["PROTECT48", "Desde cierre >= 1R: protección ajustada por coste, retención de 75% del máximo al cierre y trailing de 1R; cola causal. Máximo 48 h."],
        ["RUNNER72", "Un cuarto entero a 2R; remanente con trailing puro de 2R desde 2R. Cola causal. Máximo 72 h."],
        ["FAST24", "Reglas nativas; después de 6 h, máximo de cierres < 0,5R y último cierre <= entrada habilitan salida a siguiente apertura. Máximo 24 h."],
    ]
    return [*title("01", "Diseño y reglas congeladas"),
        p(f"Cuenta continua de {usd(p_['limits']['capitalUsd'])}, compartida por SYNA y SYNB; SYNM es referencia. "
          f"El banco combina {p_['generator']['warmup_sessions']} sesiones de calentamiento, "
          f"{p_['generator']['evaluation_sessions']} de evaluación y {p_['generator']['buffer_sessions']} de margen. "
          "Cada sesión contiene 78 barras de cinco minutos; cada barra, ocho subpasos."),
        table(["Ámbito", "Contrato"], [
            ["Información", "Solo prefijos observables de precio y volumen; sin acceso al mundo, drift ni régimen oculto."],
            ["Mundos", "TREND: persistencia; WEAK: ventaja débil; FALSE: ruptura y reversión; NULL: nulo compensado; GAP: saltos adversos."],
            ["Admisión y riesgo", "12% bruto y por activo; 0,25% riesgo abierto; 2% pérdida por sesión y 8% drawdown observado. Excesos posteriores por mercado se diagnostican por separado."],
            ["Ejecución", "Acciones enteras, IOC causal de 30 pb y contabilidad nativa. Stop adverso primero en una barra ambigua; las órdenes nuevas usan solo datos recibidos."],
        ], [92, W - 92]),
        h("Tres entradas causales"), table(["Entrada", "Especificación"], entries, [90, W - 90]),
        h("Cuatro salidas"), table(["Salida", "Especificación"], exits, [90, W - 90]),
        p("R es la distancia inicial de riesgo de precio. Riesgos por campaña: 0,0625%, 0,125% y 0,25%. "
          "Los límites de admisión no garantizan una pérdida máxima ante gaps ni fuerzan rebalanceo continuo. "
          "La regla detallada y vinculante está en [P] y [M].", "note")]


def final_comparison(e: Evidence, charts: dict[str, Path]) -> list[Any]:
    rows = []
    for world in WORLDS:
        for scenario in SCENARIOS:
            values = []
            for policy in (e.selected, *CONTROLS):
                g = e.group(world, scenario, policy)
                values.append(p(f"{pct(g['mean_return'], 3, True)}<br/>DD p95 {pct(g['p95_drawdown'], 3)}", "cell", True))
            rows.append([world, "Nominal" if scenario == "NOMINAL" else "Estrés", *values])
    return [*title("02", "Resultados finales por mundo"),
        p(f"Cada celda muestra rentabilidad terminal neta media y percentil 95 del drawdown por eventos, "
          f"sobre {e.final['statistics']['independent_seeds']} semillas. El periodo es de {e.calendar_days} días; "
          "se mantienen emparejadas las políticas y los costes. [F]"),
        table(["Mundo", "Coste", "Seleccionada", "CURRENT", "SIMPLE", "CASH"], rows,
              [52, 47, (W - 99) / 4, (W - 99) / 4, (W - 99) / 4, (W - 99) / 4]),
        Spacer(1, 4 * mm), plot_image(charts["final"], 75 * mm),
        p("CURRENT conserva la política confirmada nativa. SIMPLE es la referencia sencilla registrada. "
          "CASH permanece sin posiciones y paga el mismo coste fijo. DD p95 no es el peor drawdown observado. "
          "Las diferencias de drawdown son descriptivas: no se registró un contraste inferencial sobre ellas.", "note")]


def intervals(e: Evidence) -> list[Any]:
    rows = []
    for world in WORLDS:
        for scenario in SCENARIOS:
            cells = []
            for control in ENDPOINTS:
                v = e.final["endpoints"][f"{world}:{scenario}:{control}"]
                col = RED.hexval() if v["lower"] <= 0 else GREEN.hexval()
                cells.append(p(f"<b>{bp(v['mean'])}</b><br/><font color='{col}'>[{bp(v['lower'])}; {bp(v['upper'])}]</font>", "cellsmall", True))
            rows.append([world, "Nom." if scenario == "NOMINAL" else "Estrés", *cells])
    stats = e.final["statistics"]
    fail = len(e.final["economic_failed_gates"])
    return [*title("03", "Inferencia final: 40 contrastes"),
        p("La unidad de remuestreo es la trayectoria completa de una semilla. Los activos, las políticas y los costes "
          "se conservan emparejados. Se aplican 20.000 réplicas bootstrap y Bonferroni a cinco mundos, dos costes "
          "y cuatro contrastes. La magnitud es log-crecimiento neto por día calendario. [P, F]"),
        table(["Mundo", "Coste", "Absoluto", "vs CURRENT", "vs SIMPLE", "vs CASH"], rows,
              [51, 43, (W - 94) / 4, (W - 94) / 4, (W - 94) / 4, (W - 94) / 4], small=True),
        p("Celdas: media [cota inferior; cota superior], en pb de log-crecimiento diario. "
          "La decisión contractual utiliza la cota inferior L. Las dos cotas usan 0,00125 por cola; "
          "el par [L; U] no representa un intervalo bilateral familiar del 95%.", "note"),
        h("Interpretación del contrato"),
        p(f"La confianza familiar nominal unilateral es {pct(stats['nominal_family_confidence'], 0)}; "
          f"el alfa por endpoint es {number(stats['per_endpoint_alpha'], 5)}. Hay "
          f"{number(stats['approx_tail_replicates'], 0)} réplicas bootstrap esperadas en cada cola extrema. "
          "La cobertura es aproximada; depende de la muestra y no equivale a una garantía de mercado."),
        box("La decisión combina todas las puertas", f"Fallan {fail} criterios económicos. "
            "El contrato exige L > 1 pb/día en nominal y L > 0 bajo estrés para TREND y WEAK, "
            "además de mejora emparejada frente a los tres controles. Un score de desarrollo no positivo "
            "impide promoción aunque algún resultado final aislado parezca favorable."),
        h("Riesgo y tamaño muestral"),
        p(f"Se observan {e.final['observed_candidate_risk_violations']} incumplimientos del criterio combinado de riesgo "
          "de la seleccionada. Si un mundo y coste tienen cero fallos en 64 trayectorias, el límite binomial "
          f"unilateral del 95% para la probabilidad de fallo es {pct(e.final['zero_violations_per_64_paths_one_sided95_upper_probability'], 2)}. "
          "La cota se refiere a este horizonte y a la ley del generador."),
        p("No se anualizan retornos ni se presenta el ranking de desarrollo como intervalo confirmatorio.", "note")]


def exploration(e: Evidence, charts: dict[str, Path]) -> list[Any]:
    c = e.final["candidate"]
    pareto_count = sum(x["pareto"] for x in e.development["candidates"])
    positive = sum(g["mean_net_usd"] > 0 for k, g in e.development["groups"].items() if k.split(":", 1)[0] not in CONTROLS)
    cash_score = e.control_score("CASH")
    return [*title("04", "Frontera de exploración y selección"),
        p("Cada punto corresponde a una de las 36 recetas congeladas. La frontera se calcula únicamente entre "
          "candidatos factibles según riesgo, plazo y conciliación en desarrollo. El tamaño del punto indica "
          "riesgo por campaña; los colores distinguen entradas. [D]"),
        plot_image(charts["frontier"], 115 * mm),
        table(["Receta seleccionada", "Score robusto", "Media nominal TREND/WEAK", "DD p95 estrés"], [[
            e.selected, bp(c["score"]) + " pb/día", bp(c["mean_nominal_edge_daily_log"]) + " pb/día",
            pct(c["p95_stress_drawdown"], 3)]], [W * .36, W * .22, W * .23, W * .19]),
        h("Qué permite afirmar esta frontera"),
        p(f"Hay {pareto_count} recetas en Pareto y {positive} de 360 medias netas positivas. "
          "Pareto identifica compromisos dentro del catálogo observado: una receta puede ser no dominada "
          "y seguir perdiendo dinero. La selección maximiza el mínimo de media menos 1,645 errores estándar "
          "entre TREND/WEAK y ambos costes; ese cálculo se usa solo para ordenar desarrollo."),
        p(f"El score equivalente de CASH con los mismos costes es {bp(cash_score)} pb/día, frente a "
          f"{bp(c['score'])} de la seleccionada. " +
          ("CASH obtiene el score mayor. La receta elegida describe una reducción relativa de daños entre estrategias de trading, no un óptimo económico global."
           if cash_score > c["score"] else "La comparación con CASH se conserva explícitamente junto con la cuadrícula de trading.")),
        p("Las semillas finales permanecieron separadas de esta selección. Reutilizarlas para ajustar otra receta convertiría ese conjunto en desarrollo.", "note")]


def cost_science(e: Evidence) -> list[Any]:
    rows = []
    for world in WORLDS:
        for scenario in SCENARIOS:
            g = e.group(world, scenario)
            rows.append([world, "Nom." if scenario == "NOMINAL" else "Estrés",
                         number(g["mean_price_pnl_after_friction_usd"]), number(g["mean_fees_usd"]),
                         number(g["mean_fixed_cost_usd"]), number(g["mean_net_usd"])])
    capital = e.protocol["limits"]["capitalUsd"]
    notional = capital * e.protocol["limits"]["grossFraction"]
    costs = [e.group("TREND", s, "CASH")["mean_fixed_cost_usd"] for s in SCENARIOS]
    null_rows = []
    for s in SCENARIOS:
        for endpoint in ("ABSOLUTE", "CASH"):
            v = e.final["endpoints"][f"NULL:{s}:{endpoint}"]
            null_rows.append([s, "Absoluto" if endpoint == "ABSOLUTE" else "vs CASH", bp(v["mean"]), bp(v["lower"])])
    return [*title("05", "Costes, nulo y sostenibilidad"),
        p("Descomposición de la seleccionada: medias por cuenta, en USD. El PnL de precio ya incorpora "
          "spread y slippage; se restan después comisiones y costes fijos. No se inventa una descomposición "
          "exacta de spread y slippage a partir de precios redondeados. [F]"),
        table(["Mundo", "Coste", "Precio neto de fricción", "Comisiones", "Fijos", "PnL neto"], rows,
              [52, 47, 110, 90, 80, W - 379]),
        p(f"CASH soporta {usd(costs[0])} en nominal y {usd(costs[1])} en estrés durante {e.calendar_days} días. "
          f"Como referencia contable simplificada, esos gastos equivalen a {pct(costs[0] / notional, 2)} y "
          f"{pct(costs[1] / notional, 2)} del notional inicial máximo de {usd(notional)}. "
          "La comparación supone ese notional constante y omite comisiones; no es un límite formal para carteras dinámicas.", "small"),
        h("NULL: control de especificación y sesgo"),
        table(["Coste", "Contraste", "Media (pb/día)", "Cota inferior"], null_rows, [90, 110, 145, W - 345]),
        p("NULL usa una mezcla compensada sin drift explotable. Bajo un precio martingala y una estrategia "
          "autofinanciada causal, los costes no crean ventaja. Los fills interpolados de OHLC son una aproximación "
          "adicional: una cota inferior positiva en NULL activaría una revisión de ejecución, fuga de datos "
          "y contabilidad, además del generador. Superar este control no demuestra ausencia de todo sesgo."),
        p("Una referencia externa de efectivo sin plataforma tendría coste fijo cero. Esa referencia no fue "
          "una cuenta del experimento registrado; ayuda a interpretar por qué reducir pérdidas no basta "
          "para justificar mantener un sistema con costes. [P, M]", "note")]


def framework_route(text: str) -> list[tuple[str, str]]:
    section = re.search(r"## 7\..*?\n(.*?)(?=\n## 8\.|\Z)", text, re.S)
    if not section:
        raise ValueError("FRAMEWORK_OPERATIONAL_ROUTE_SECTION_REQUIRED")
    result = []
    for line in section.group(1).splitlines():
        match = re.match(r"\d+\. \*\*(.*?)\*\*[:.]?\s*(.*)", line)
        if match:
            head = match.group(1).rstrip(":.")
            body = match.group(2).split(". ")[0].rstrip(".") + "."
            result.append((head, body))
    if len(result) != 6:
        raise ValueError("FRAMEWORK_SIX_OPERATIONAL_STEPS_REQUIRED")
    return result


def gates(e: Evidence) -> list[Any]:
    missing = set(e.final["framework_missing_before_measurement"])
    rows = []
    for key in GATE_LABELS:
        value = e.final["gates"][key]
        status = p(f"<b><font color='{GREEN.hexval() if value else RED.hexval()}'>{'CUMPLE' if value else 'FALLA'}</font></b>", "cell", True)
        rows.append(["Operativo" if key in missing else "Económico", GATE_LABELS[key], status])
    route = framework_route(e.framework)
    out = [*title("06", "Puertas de aceptación y trabajo"),
           p("La etiqueta N9-S es un contrato interno: se admite si y solo si todas las puertas predefinidas "
             "son verdaderas. La factibilidad económica se informa separadamente de las brechas operativas. "
             "Esta regla lógica no demuestra rentabilidad en mercados reales. [P, F, M]"),
           table(["Ámbito", "Condición", "Estado"], rows, [67, W - 138, 71]),
           h("Ruta operativa del framework"),
           table(["Paso", "Siguiente trabajo verificable"], [[str(i + 1), f"{head}. {body}"]
                 for i, (head, body) in enumerate(route)], [34, W - 34], small=True),
           p("Los pasos son una ruta propuesta, no procesos ya desplegados. Cualquier nueva búsqueda requiere "
             "prerregistro, presupuesto y validación nuevos; se conserva el resultado negativo de este ciclo.", "note")]
    return out


def modulation_table(e: Evidence, start: int, stop: int, include_controls: bool) -> list[Any]:
    all_rows = e.development["candidates"]
    rows, highlighted = [], set()
    for i, r in enumerate(all_rows[start:stop], start):
        state = "Fuera riesgo" if not r["risk_feasible"] else "Pareto" if r["pareto"] else "Dominada"
        if r["duplicates_current"]:
            state = "Dup. CURRENT"
        if r["id"] == e.selected:
            state = "Seleccionada"
            highlighted.add(i - start)
        rows.append([f"{i + 1:02}", r["entry"], r["exit"], pct(r["risk"], 4),
                     bp(r["mean_nominal_edge_daily_log"]), bp(r["score"]),
                     pct(r["p95_stress_drawdown"], 3), state])
    index = "07" if start == 0 else "08"
    out = [*title(index, f"Catálogo completo: recetas {start + 1}-{stop}"),
           p("Resultados de desarrollo. No son evidencia confirmatoria. Riesgo es la fracción de equity "
             "admitida por campaña; μN y score se expresan en pb de log-crecimiento por día calendario. [D]"),
           table(["N.º", "Entrada", "Salida", "Riesgo", "μN", "Score", "DD p95\nestrés", "Estado"], rows,
                 [24, 70, 70, 56, 54, 57, 67, W - 398], small=True, highlights=highlighted),
           p("μN: media nominal de TREND y WEAK. Score: mínimo de media menos 1,645 errores estándar "
             "entre ambos mundos y costes. DD p95: percentil 95 de todos los mundos bajo STRESS. "
             "Pareto se evalúa solo entre candidatos factibles. El duplicado de CURRENT se contabiliza "
             "y se excluye de la selección como mejora.", "note")]
    if include_controls:
        controls = []
        for control in CONTROLS:
            nominal = np.mean([e.group(w, "NOMINAL", control, "development")["mean_daily_log"] for w in ("TREND", "WEAK")])
            worst = max(e.group(w, "STRESS", control, "development")["worst_drawdown"] for w in WORLDS)
            controls.append([control, bp(float(nominal)), bp(e.control_score(control)), pct(worst, 3)])
        out += [h("Controles no seleccionables de desarrollo"),
                table(["Control", "μN (pb/día)", "Score (pb/día)", "Peor DD estrés"], controls,
                      [105, 125, 125, W - 355]),
                p("En esta tabla de controles se informa el peor drawdown observado. Es distinto del percentil 95 "
                  "agregado utilizado para las 36 recetas. CURRENT es la política nativa; SIMPLE y CASH son "
                  "referencias registradas. Ningún control se omite del contraste final.", "note")]
    return out


def integrity(e: Evidence) -> list[Any]:
    groups = e.candidate_groups()
    max_reconciliation = max(g["maximum_reconciliation_error_usd"] for g in e.final["groups"].values())
    ci_url = f"{REPO}/actions/runs/{e.qa['run_id']}"
    review = e.independent
    independent_text = "Revisión ampliada no incorporada."
    exposure_text = "Los excesos de exposición por precio se informan como diagnóstico de admisión."
    if review:
        stages = review["audit"]["stages"]
        totals = {key: sum(stage[key] for stage in stages.values()) for key in
                  ("accounts", "closed_campaigns", "exit_fills", "retained_session_curve_points")}
        maximum_decimal_error = review["audit"]["maximum_errors_over_both_stages"]["terminal_equity_usd"]
        independent_text = (f"{number(totals['accounts'], 0)} cuentas, {number(totals['closed_campaigns'], 0)} campañas, "
                            f"{number(totals['exit_fills'], 0)} fills de salida y {number(totals['retained_session_curve_points'], 0)} "
                            f"puntos de curva. Reconstrucción Decimal: error máximo de equity {maximum_decimal_error:.2e} USD. "
                            f"{review['binding']['registered_source_files_verified']} fuentes con SHA-256 verificado. [I]")
        risk = review["risk_summaries"]["final"][e.selected]
        exposure_text = (f"En {risk['observed_event_gross_overage_accounts']} de {risk['accounts']} cuentas finales de la receta "
                         f"se observó exposición marcada superior al 12%; máximo {pct(risk['maximum_event_gross_fraction'], 4)}. "
                         "El 12% es un límite de admisión/reserva, no una cota continua después de mover el precio. "
                         f"Déficits de efectivo informados: {risk['observed_cash_deficit_accounts']}; "
                         f"excesos de riesgo reservado: {risk['observed_event_risk_overage_accounts']}. [I]")
    legacy_quant = next((run for run in (e.legacy or {}).get("failed_runs", []) if "tests_run" in run), None)
    legacy_summary = (f"suite quant de {number(legacy_quant['tests_run'], 0)} pruebas, "
                      f"{legacy_quant['errors']} errores. ") if legacy_quant else ""
    out = [*title("09", "Forense, validación y límites"),
        h("Trailing legado: diferencia técnica identificada"),
        p("Con availableAt = end + 1 s, la apertura inmediatamente siguiente todavía no conoce el cierre "
          "recién terminado. La implementación nativa puede reemplazar su único stop pendiente con otro "
          "de recepción posterior; la activación puede posponerse reiteradamente hasta el salto nocturno. "
          "Existe un fixture que reproduce esta conducta y confirma equivalencia exacta con NATIVE72."),
        p("NATIVE72 y FAST24 preservan la semántica heredada. PROTECT48 y RUNNER72 mantienen una cola de "
          "actualizaciones y aplican solo las recibidas. Sus diferencias combinan modulación económica y "
          "reparación causal; para separar las contribuciones se necesita una ablación registrada. [M]"),
        h("Evidencia ejecutada y alcance de QA"),
        table(["Comprobación", "Evidencia y alcance"], [
            ["Pruebas de este alcance", f"{e.qa['python_unit_tests']} Python + {e.qa['node_unit_tests']} Node; "
             "Ruff y mypy: " + e.qa["ruff"] + "/" + e.qa["mypy"] + ". No constituyen aprobación de producción."],
            ["CI del alcance", p(f"<link href='{ci_url}'>Run {e.qa['run_id']}</link> · conclusión {esc(e.qa['conclusion'])}. "
             "La búsqueda económica no corrió en CI.", "cell", True)],
            ["Integridad", "Protocolo, fuentes, semillas, selección y artefactos vinculados mediante SHA-256. "
             "Auditoría independiente en Python de curva, trades, costes y denominador diario."],
            ["Conciliación final", f"Máximo error absoluto del analizador: {max_reconciliation:.2e} USD. "
             "Inventarios terminales conciliados según el analizador."],
            ["Riesgo seleccionado", f"Peor DD {pct(max(g['worst_drawdown'] for g in groups), 4)}; "
             f"peor sesión {pct(min(g['worst_session_return'] for g in groups), 4)}; "
             f"plazo máximo {number(max(g['max_hold_hours'] for g in groups), 4)} h."],
            ["Revisión separada", independent_text],
            ["Exposición marcada", exposure_text],
            ["Revisión ampliada", "Controles de procedencia heredados permanecen bloqueados: " + legacy_summary +
             "Un conflicto PROFIT8 ya precedía a esta rama; los dos errores de evidence_scope se relacionan "
             "con la nueva huella del motor opt-in. No todas las suites del repositorio pasan."],
        ], [112, W - 112]),
        p("El CI focalizado de 128 pruebas y las incidencias de la revisión ampliada tienen alcances diferentes. "
          "La reconstrucción aritmética fue realizada por otro agente del mismo equipo; no es auditoría externa. "
          "No reejecutó independientemente toda la trayectoria intrabar de eventos. " +
          ("El diagnóstico ampliado se conserva en [L]." if e.legacy else
           "El detalle ampliado fue comunicado por el orquestador; el generador de este informe no reejecutó esa suite."), "note"),
        h("Brechas que permanecen abiertas"),
        p("El modelo de ejecución no cubre por completo parciales de entrada, rechazos, cancelaciones, "
          "impacto, interrupciones y evidencia de profundidad. La matriz virtual no está integrada como "
          "coordinador completo. El generador no está calibrado a mercados observados y omite feriados "
          "y horario estacional. Los límites de admisión no liquidan automáticamente excesos posteriores."),
        p(f"La deuda del presupuesto histórico permanece sin conciliación: "
          f"{e.protocol['budget']['historical_reserved_plus_unincorporated']} frente a "
          f"{e.protocol['budget']['historical_cap']}. El suplemento actual cuenta por separado "
          f"{e.development['account_count'] + e.final['account_count']} cuentas. [P, R]", "note")]
    return out


def references(e: Evidence) -> list[Any]:
    rows = []
    for key in ("D", "F", "P", "R", "M", "Q", "I"):
        if key not in e.files:
            continue
        path = e.files[key]
        digest = sha(path)
        rows.append([f"[{key}] {path.relative_to(e.root)}",
                     p(digest[:32] + "<br/>" + digest[32:], "mono", True)])
    links = [
        ("Protocolo congelado", f"{REPO}/blob/{e.qa['commit']}/research/modulation9/protocol.json"),
        ("Implementación y analizador", f"{REPO}/blob/{e.qa['commit']}/tools/analyze_modulation9.py"),
        ("Framework completo", f"{REPO}/blob/{BRANCH}/docs/MODULATION9_FRAMEWORK.md"),
        ("Artefactos de investigación", f"{REPO}/tree/{BRANCH}/evidence/modulation9"),
        ("CI focalizado", f"{REPO}/actions/runs/{e.qa['run_id']}"),
    ]
    academic = re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", e.framework)
    out = [*title("10", "Fuentes y reproducción"),
        p("La tabla identifica los bytes locales utilizados para este informe. Los repositorios contienen "
          "el código y la ruta de reproducción; la vigencia de resultados se liga a los hashes, no al nombre "
          "de una rama mutable. La selección se congeló antes del final."),
        table(["Fuente", "SHA-256"], rows, [W - 193, 193], small=True),
        h("Rutas del proyecto y CI")]
    for label, url in links:
        out.append(p(f"<b>{esc(label)}</b>: <link color='#087F8C' href='{esc(url)}'>{esc(url)}</link>", "small", True))
    if e.legacy:
        out.append(p(f"[L] Diagnóstico ampliado: {e.files['L'].relative_to(e.root)}", "small"))
    if "S" in e.files:
        out.append(p(f"[S] Discusión de resultados y decisiones: {e.files['S'].relative_to(e.root)}", "small"))
    out.append(h("Fundamentos metodológicos citados en el framework"))
    for label, url in academic[:3]:
        label = label.replace("*", "")
        out.append(p(f"<link color='#087F8C' href='{esc(url)}'>{esc(label)}</link> · {esc(url)}", "small", True))
    out += [p("Estas referencias motivan el control de costes, drawdown y selección. Este banco no implementa "
              "el programa convexo de Risk-Constrained Kelly ni midió PBO/CSCV; no hereda garantías de esos métodos.", "note"),
            h("Verificación reproducible"),
            p("PYTHONPATH=quant python -m unittest discover -s quant/tests -p 'test_modulation9*.py' -v", "mono"),
            Spacer(1, 2 * mm),
            p("node --test tools/modulation9_test.cjs tools/profit8_replay_test.cjs", "mono"),
            Spacer(1, 3 * mm),
            p("El framework [M] contiene comandos completos para reproducir las dos etapas en directorios nuevos. "
              "Una nueva optimización exige otro registro.", "note")]
    return out


def build_report(e: Evidence, output: Path) -> dict[str, Any]:
    setup_fonts()
    output.parent.mkdir(parents=True, exist_ok=True)
    charts = create_charts(e, output.parent / "figures")
    sections = [cover(e), design(e), final_comparison(e, charts), intervals(e), exploration(e, charts),
                cost_science(e), gates(e), modulation_table(e, 0, 18, False),
                modulation_table(e, 18, 36, True), integrity(e), references(e)]
    story: list[Any] = []
    for i, section in enumerate(sections):
        if i:
            story.append(PageBreak())
        story.extend(section)
    doc = SimpleDocTemplate(str(output), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=21 * mm, bottomMargin=21 * mm,
                            title="HarpoonX - Modulacion 9: evidencia sintetica y framework",
                            author="HarpoonX | Investigacion y analisis", subject="Resultados sinteticos, riesgo, rentabilidad y validacion")
    doc.build(story, onFirstPage=page_header, onLaterPages=page_header, canvasmaker=NumberedCanvas)
    reader = PdfReader(str(output))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    required = [e.selected, "NO_GO" if e.final["verdict"] == "NO_GO" else e.final["verdict"],
                "36", "CURRENT", "SIMPLE", "CASH", "40 contrastes", "SHA-256"]
    if any(token not in text for token in required):
        raise ValueError("REPORT_TEXT_COMPLETENESS")
    metrics = {"pdf": str(output), "pages": len(reader.pages), "pdf_sha256": sha(output),
               "source_sha256": {key: sha(path) for key, path in e.files.items()},
               "generator_sha256": sha(Path(__file__)), "candidate_id": e.selected,
               "economic_model_feasibility": e.final["economic_model_feasibility"],
               "conditional_n9s_accepted": e.final["conditional_n9s_accepted"],
               "calendar_days": e.calendar_days, "page_count_target_met": 8 <= len(reader.pages) <= 12,
               "text_completeness": True, "visual_review_required": True,
               "charts": {key: str(path) for key, path in charts.items()},
               "marker_executed_by_generator": False}
    (output.parent / "HarpoonX_Modulacion9_Informe_20261107_manifest.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False) + "\n")
    if not metrics["page_count_target_met"]:
        raise ValueError(f"REPORT_PAGE_BUDGET:{metrics['pages']}")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--generate", action="store_true", help="Create PDF only after the one-time PDF marker succeeds.")
    args = parser.parse_args()
    e = Evidence.load(args.root)
    framework_route(e.framework)
    if args.generate:
        print(json.dumps(build_report(e, args.output), ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"status": "INPUTS_VALIDATED_NO_PDF_CREATED", "candidate_id": e.selected,
                          "calendar_days": e.calendar_days, "marker_executed": False,
                          "final_verdict": e.final["verdict"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
