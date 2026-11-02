"""Timestamp-aligned correlation surfaces and a segregated, immutable vector registry."""

from __future__ import annotations

import json
import sqlite3
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np

from .core import covariance, digest, finite, timestamp


def corr(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 4 or np.std(x) < 1e-12 or np.std(y) < 1e-12:
        raise ValueError("CORRELATION_INSUFFICIENT_VARIATION")
    return float(np.clip(np.corrcoef(x, y)[0, 1], -1, 1))


def cell(x: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    r = corr(x, y)
    persistence = corr(x[:-1], x[1:]) * corr(y[:-1], y[1:]) if len(x) >= 8 else 0
    effective = float(
        np.clip(len(x) * (1 - persistence) / max(1e-6, 1 + persistence), 4, len(x))
    )
    z = np.arctanh(np.clip(r, -0.999999, 0.999999))
    width = 1.96 / np.sqrt(max(1, effective - 3))
    bounds = np.tanh([z - width, z + width]).tolist()
    bounds[0], bounds[1] = min(bounds[0], r), max(bounds[1], r)
    return {
        "correlation": r,
        "n": len(x),
        "effective_n_approx": effective,
        "ci95_approx": bounds,
        "inference": "DESCRIPTIVE_AUTOCORRELATION_APPROX_NO_MULTIPLICITY_CONTROL",
    }


def surface(
    panel: dict[str, list[dict[str, Any]]],
    asof: str,
    *,
    feed: str,
    origin: str = "OBSERVED",
    clock: str = "LIVE_RECEIPT",
    windows: tuple[int, ...] = (32, 64, 128),
    lags: tuple[int, ...] = (-6, -3, -1, 0, 1, 3, 6),
    bar_seconds: int = 300,
    pairs: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    if origin not in ("OBSERVED", "SYNTHETIC_ENGINEERING_ONLY") or clock not in (
        "LIVE_RECEIPT",
        "EVENT_TIME_REPLAY",
    ):
        raise ValueError("SURFACE_PROVENANCE")
    if (
        not 2 <= len(panel) <= 48
        or not windows
        or len(windows) > 4
        or any(type(w) is not int or not 16 <= w <= 512 for w in windows)
    ):
        raise ValueError("SURFACE_COMPUTE_CAP")
    if (
        not lags
        or len(lags) > 15
        or any(type(v) is not int or abs(v) > 12 for v in lags)
        or len(set(lags)) != len(lags)
        or len(set(windows)) != len(windows)
    ):
        raise ValueError("SURFACE_LAGS")
    if bar_seconds <= 0:
        raise ValueError("BAR_SECONDS")
    end = timestamp(asof)
    names = sorted(panel)
    pairs = sorted(pairs if pairs is not None else list(combinations(names, 2)))
    if (
        not pairs
        or len(pairs) > 1128
        or len(set(pairs)) != len(pairs)
        or any(a == b or a not in panel or b not in panel for a, b in pairs)
    ):
        raise ValueError("SURFACE_PAIRS")
    returns: dict[str, dict[float, tuple[float, str]]] = {}
    observations: dict[str, Any] = {}
    for symbol, raw in panel.items():
        bars = sorted(
            (
                b
                for b in raw
                if timestamp(b["end"]) <= end
                and (clock == "EVENT_TIME_REPLAY" or timestamp(b["known_at"]) <= end)
            ),
            key=lambda b: timestamp(b["end"]),
        )
        if len({b["end"] for b in bars}) != len(bars):
            raise ValueError("DUPLICATE_BAR_TIME")
        if bars:
            age = (end - timestamp(bars[-1]["end"])).total_seconds()
            observations[symbol] = {"latest_end": bars[-1]["end"], "age_seconds": age}
            if clock == "LIVE_RECEIPT" and age > 2 * bar_seconds:
                raise ValueError("STALE_LIVE_CORRELATION_BARS:" + symbol)
        result = {}
        for i in range(1, len(bars)):
            previous, current = bars[i - 1], bars[i]
            if previous["session"] != current["session"] or timestamp(
                previous["end"]
            ) != timestamp(current["start"]):
                continue
            if (
                timestamp(current["end"]) - timestamp(current["start"])
            ).total_seconds() != bar_seconds:
                raise ValueError("BAR_FREQUENCY_MISMATCH")
            value = np.log(
                finite(current["close"], "CLOSE", True)
                / finite(previous["close"], "CLOSE", True)
            )
            result[timestamp(current["end"]).timestamp()] = (
                float(value),
                current["session"],
            )
        returns[symbol] = result
    cells = []
    vector = []
    feature_names = []
    diagnostics = []
    for a, b in pairs:
        for w in windows:
            for lag in lags:
                aligned = [
                    (t, v[0], returns[b][t - lag * bar_seconds][0])
                    for t, v in sorted(returns[a].items())
                    if t - lag * bar_seconds in returns[b]
                    and returns[b][t - lag * bar_seconds][1] == v[1]
                ]
                if len(aligned) < w:
                    raise ValueError(f"SURFACE_WARMUP:{a}:{b}:{w}:{lag}")
                xy = np.array([[r[1], r[2]] for r in aligned[-w:]])
                c = {
                    "pair": [a, b],
                    "window": w,
                    "lag": lag,
                    **cell(xy[:, 0], xy[:, 1]),
                }
                cells.append(c)
                vector.append(c["correlation"])
                feature_names.append(f"{a}|{b}|w{w}|lag{lag}")
                if lag == 0:
                    down = xy[:, 0] < 0
                    downside = (
                        corr(xy[down, 0], xy[down, 1]) if down.sum() >= 12 else None
                    )
                    lower = np.quantile(xy, 0.1, axis=0)
                    left = xy[:, 0] <= lower[0]
                    tail = float(np.mean(xy[left, 1] <= lower[1]))
                    d = {
                        "pair": [a, b],
                        "window": w,
                        "beta_a_on_b": float(
                            np.cov(xy.T, ddof=1)[0, 1] / np.var(xy[:, 1], ddof=1)
                        ),
                        "downside_corr_a_negative": downside,
                        "joint_lower_tail_given_a": tail,
                        "tail_sample_count": int(left.sum()),
                        "regime": "UNDETERMINED",
                    }
                    if len(aligned) >= 2 * w:
                        prior = np.array([[r[1], r[2]] for r in aligned[-2 * w : -w]])
                        pr = corr(prior[:, 0], prior[:, 1])
                        d.update(
                            prior_correlation=pr,
                            correlation_change=c["correlation"] - pr,
                            regime="DESCRIPTIVE_BREAK"
                            if abs(c["correlation"] - pr) >= 0.35
                            else "DESCRIPTIVE_STABLE",
                        )
                    diagnostics.append(d)
    common = sorted(set.intersection(*(set(returns[n]) for n in names)))
    spectrum = None
    if len(common) >= max(windows):
        matrix = np.array(
            [[returns[n][t][0] for n in names] for t in common[-max(windows) :]]
        )
        cov = covariance(matrix)
        scale = np.sqrt(np.diag(cov))
        correlation = cov / np.outer(scale, scale)
        eig = np.linalg.eigvalsh(correlation)
        if eig.min() < -1e-8:
            raise ArithmeticError("CORRELATION_NOT_PSD")
        mass = np.maximum(eig, 1e-15) / eig.sum()
        spectrum = {
            "symbols": names,
            "correlation_shrunk_psd": correlation.tolist(),
            "largest_eigen_share": float(eig[-1] / eig.sum()),
            "effective_rank": float(np.exp(-np.sum(mass * np.log(mass)))),
            "aligned_returns": len(matrix),
        }
    schema = {
        "method_version": "1.1.0",
        "feature_names": feature_names,
        "bar_seconds": bar_seconds,
        "windows": list(windows),
        "lags": list(lags),
        "positive_lag": "corr(a_t, b_t-lag); historical association, no causal claim",
    }
    return {
        "schema": "HARPOON_CORRELATION_SURFACE_1",
        "asof": asof,
        "origin": origin,
        "feed": feed,
        "clock": clock,
        "vector_schema": schema,
        "schema_hash": digest(schema),
        "vector": vector,
        "cells": cells,
        "diagnostics": diagnostics,
        "spectrum": spectrum,
        "input_hash": digest(panel),
        "observations": observations,
        "trade_authorization": False,
        "inference": "DESCRIPTIVE_ONLY; confidence approximations do not control the surface-wide search family",
    }


class CurveStore:
    """Exact local retrieval; clock, feed, provenance and vector schema never mix."""

    def __init__(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=5)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS curves(id TEXT PRIMARY KEY, at REAL NOT NULL, known REAL NOT NULL, origin TEXT NOT NULL, feed TEXT NOT NULL, clock TEXT NOT NULL, schema_hash TEXT NOT NULL, vector BLOB NOT NULL, payload TEXT NOT NULL)"
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS curve_time ON curves(schema_hash,origin,feed,clock,at,known)"
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def add(self, curve: dict[str, Any], known_at: str) -> str:
        validate_surface(curve)
        vector = np.asarray(curve["vector"], dtype="<f8")
        if (
            vector.ndim != 1
            or not 1 <= len(vector) <= 50000
            or not np.isfinite(vector).all()
            or np.any(np.abs(vector) > 1 + 1e-10)
        ):
            raise ValueError("CURVE_VECTOR_DOMAIN")
        if len(vector) != len(curve["vector_schema"]["feature_names"]) or curve[
            "schema_hash"
        ] != digest(curve["vector_schema"]):
            raise ValueError("CURVE_SCHEMA_HASH")
        if curve["origin"] not in ("OBSERVED", "SYNTHETIC_ENGINEERING_ONLY") or curve[
            "clock"
        ] not in ("LIVE_RECEIPT", "EVENT_TIME_REPLAY"):
            raise ValueError("CURVE_PROVENANCE")
        at, known = (
            timestamp(curve["asof"]).timestamp(),
            timestamp(known_at).timestamp(),
        )
        if known < at:
            raise ValueError("CURVE_KNOWN_BEFORE_DECISION")
        payload = json.dumps(
            {"curve": curve, "known_at": known_at}, sort_keys=True, allow_nan=False
        )
        if len(payload.encode()) > 8 * 1024 * 1024:
            raise ValueError("CURVE_PAYLOAD_SIZE_BOUND")
        identity = digest(json.loads(payload))
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO curves VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    identity,
                    at,
                    known,
                    curve["origin"],
                    curve["feed"],
                    curve["clock"],
                    curve["schema_hash"],
                    vector.tobytes(),
                    payload,
                ),
            )
        return identity

    def _check(self, row: tuple) -> dict[str, Any]:
        identity, at, known, origin, feed, clock, schema, blob, payload = row
        data = json.loads(payload)
        c = data["curve"]
        vector = np.frombuffer(blob, dtype="<f8")
        if (
            digest(data) != identity
            or c["schema_hash"] != schema
            or c["origin"] != origin
            or c["feed"] != feed
            or c["clock"] != clock
            or timestamp(c["asof"]).timestamp() != at
            or timestamp(data["known_at"]).timestamp() != known
            or not np.array_equal(vector, np.asarray(c["vector"]))
        ):
            raise ValueError("CURVE_INTEGRITY_FAILURE")
        return data

    def get(self, identity: str) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM curves WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise KeyError(identity)
        return self._check(row)

    def nearest(
        self,
        curve: dict[str, Any],
        available_at: str,
        *,
        k: int = 5,
        embargo_seconds: float = 86400,
        metric: str = "rms",
    ) -> dict[str, Any]:
        validate_surface(curve)
        if not 1 <= k <= 100 or embargo_seconds < 0 or metric not in ("rms", "cosine"):
            raise ValueError("NEIGHBOR_QUERY_DOMAIN")
        target = np.asarray(curve["vector"], dtype=float)
        if not np.isfinite(target).all() or target.ndim != 1:
            raise ValueError("QUERY_VECTOR")
        now = timestamp(available_at).timestamp()
        cutoff = min(timestamp(curve["asof"]).timestamp(), now) - embargo_seconds
        rows = self.db.execute(
            "SELECT * FROM curves WHERE schema_hash=? AND origin=? AND feed=? AND clock=? AND at<? AND known<=? ORDER BY at DESC,known DESC,id LIMIT 5001",
            (
                curve["schema_hash"],
                curve["origin"],
                curve["feed"],
                curve["clock"],
                cutoff,
                now,
            ),
        )
        truncated = False
        results = []
        decisions = set()
        scanned, used_bytes = 0, 0
        for row in rows:
            size = len(row[7]) + len(row[8].encode())
            if scanned >= 5000 or used_bytes + size > 32 * 1024 * 1024:
                truncated = True
                break
            scanned += 1
            used_bytes += size
            c = self._check(row)["curve"]
            if row[1] in decisions:
                continue
            decisions.add(row[1])
            v = np.asarray(c["vector"])
            if v.shape != target.shape:
                raise ValueError("VECTOR_DIMENSION_MISMATCH")
            if metric == "rms":
                distance = float(np.sqrt(np.mean((v - target) ** 2)))
            else:
                denominator = np.linalg.norm(v) * np.linalg.norm(target)
                distance = (
                    float(np.clip(1 - np.dot(v, target) / denominator, 0, 2))
                    if denominator
                    else (0.0 if np.array_equal(v, target) else 1.0)
                )
            results.append({"id": row[0], "asof": c["asof"], "distance": distance})
        results.sort(key=lambda x: (x["distance"], x["id"]))
        return {
            "neighbors": results[:k],
            "metric": metric,
            "searched": scanned,
            "payload_bytes_scanned": used_bytes,
            "search_truncated": truncated,
            "scope": "Exact search within 5000 prior rows and a 32MiB payload budget, segregated by schema/feed/origin/clock. Latest available revision per decision. Similarity is not predictive edge.",
        }


def validate_surface(curve: dict[str, Any]) -> None:
    if curve.get("schema") != "HARPOON_CORRELATION_SURFACE_1" or curve.get(
        "schema_hash"
    ) != digest(curve["vector_schema"]):
        raise ValueError("SURFACE_SCHEMA_INTEGRITY")
    vector = np.asarray(curve["vector"], dtype=float)
    names = curve["vector_schema"]["feature_names"]
    cells = curve["cells"]
    if (
        vector.ndim != 1
        or len(vector) != len(names)
        or len(cells) != len(names)
        or not np.isfinite(vector).all()
        or np.any(np.abs(vector) > 1 + 1e-10)
    ):
        raise ValueError("SURFACE_VECTOR_INTEGRITY")
    for name, value, c in zip(names, vector, cells, strict=True):
        expected = f"{c['pair'][0]}|{c['pair'][1]}|w{c['window']}|lag{c['lag']}"
        lo, hi = c["ci95_approx"]
        if (
            name != expected
            or value != c["correlation"]
            or c["n"] < c["window"]
            or not -1 <= lo <= value <= hi <= 1
        ):
            raise ValueError("SURFACE_CELL_INTEGRITY")
