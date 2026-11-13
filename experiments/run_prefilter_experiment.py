"""Experiment B-2: 10-seed GPS stress test with and without prefiltering.

Addresses the limitations stated for Experiment B (single seed per condition,
no filtering): every Experiment-B condition is repeated over 10 independent
seeds for four pipelines (raw, Hampel, gated Kalman, Hampel+Kalman). The
Geo-fencing + Isolation Forest detector is re-fitted per pipeline on filtered
train/validation trajectories (400 / 150, 3.5 m noise) so the preprocessing is
part of the pipeline and thresholds are re-calibrated; test trajectories are
200 per condition per seed. Results -> results/prefilter_results.json/.md
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from tourist_safety.anomaly import HybridGeofenceIFDetector
from tourist_safety.preprocess import PIPELINES, apply_pipeline
from tourist_safety.simulator import default_test_geography, generate_dataset
from run_experiments import _classification_metrics, _featurize

SEEDS = list(range(601, 611))  # 10 independent seeds, disjoint from Exp. A/ablation seeds
CONDITIONS = [
    ("2 m GPS error", dict(gps_noise_m=2.0)),
    ("5 m GPS error", dict(gps_noise_m=5.0)),
    ("10 m GPS error", dict(gps_noise_m=10.0)),
    ("15 m GPS error", dict(gps_noise_m=15.0)),
    ("30% dropout", dict(gps_noise_m=3.0, dropout_prob=0.30)),
    ("15% jump spikes", dict(gps_noise_m=3.0, jump_prob=0.15)),
]
ZONES, _ = default_test_geography()


def ci95(vals: list[float]) -> tuple[float, float]:
    a = np.asarray(vals, dtype=float)
    sd = float(np.std(a, ddof=1)) if len(a) > 1 else 0.0
    return float(a.mean()), 1.96 * sd / math.sqrt(len(a))


def fit_pipeline(name: str) -> HybridGeofenceIFDetector:
    tr = [apply_pipeline(t, name, ZONES) for t in generate_dataset(400, seed=42, gps_noise_m=3.5)]
    va = [apply_pipeline(t, name, ZONES) for t in generate_dataset(150, seed=108, gps_noise_m=3.5)]
    X_tr, _, _ = _featurize([t for t in tr if not t.is_anomalous])
    X_va, y_va, c_va = _featurize(va)
    return HybridGeofenceIFDetector(n_estimators=200, contamination=0.08, random_state=42).fit(
        X_tr, X_va, y_va, c_va
    )


def main() -> None:
    results: dict[str, dict[str, dict[str, dict[str, float]]]] = {}
    for name in PIPELINES:
        model = fit_pipeline(name)
        results[name] = {}
        for cond, kw in CONDITIONS:
            per = {"precision": [], "recall": [], "f1_score": [], "false_alerts_per_hour": []}
            for s in SEEDS:
                ds = [apply_pipeline(t, name, ZONES) for t in generate_dataset(200, seed=s, **kw)]
                X, y, ctx = _featurize(ds)
                m = _classification_metrics(y, model.predict(X, ctx), model.score(X, ctx))
                for k in per:
                    per[k].append(m[k])
            results[name][cond] = {
                k: dict(zip(("mean", "ci95"), map(lambda v: round(v, 4), ci95(v)))) for k, v in per.items()
            }
        print("done", name, flush=True)

    out = Path(__file__).resolve().parent / "results"
    (out / "prefilter_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    lines = ["# Experiment B-2: GPS Prefiltering, 10 seeds x 200 trajectories/condition (mean ± 95% CI)", ""]
    for metric, title in (("f1_score", "F1-score"), ("false_alerts_per_hour", "False alerts / tourist-hour"),
                          ("recall", "Recall")):
        lines += [f"## {title}", "", "| Condition | " + " | ".join(PIPELINES) + " |",
                  "| --- | " + " | ".join(["---:"] * len(PIPELINES)) + " |"]
        for cond, _ in CONDITIONS:
            row = [f"{results[p][cond][metric]['mean']:.3f} ± {results[p][cond][metric]['ci95']:.3f}"
                   if metric != "false_alerts_per_hour"
                   else f"{results[p][cond][metric]['mean']:.2f} ± {results[p][cond][metric]['ci95']:.2f}"
                   for p in PIPELINES]
            lines.append(f"| {cond} | " + " | ".join(row) + " |")
        lines.append("")
    (out / "prefilter_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
