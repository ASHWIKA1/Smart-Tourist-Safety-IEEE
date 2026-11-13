"""10-Seed Statistical Confidence Intervals and Feature Ablation Study.

Addresses reviewer requests for:
1. Multi-seed evaluation (10 independent random seeds) with mean, std, and 95% CI.
2. Feature ablation comparing speed-only, stop-duration-only, route-deviation-only,
   speed+stop, and all 7 movement features for Isolation Forest and LOF.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from tourist_safety.anomaly import (
    HybridGeofenceIFDetector,
    IsolationForestDetector,
    LOFDetector,
    RuleBasedDetector,
)
from tourist_safety.simulator import generate_dataset
from run_experiments import _classification_metrics, _compute_detection_delay_s, _featurize


SEEDS = list(range(101, 111))  # 10 independent seeds

FEATURE_SUBSETS: dict[str, list[int]] = {
    "Speed only (3)": [0, 1, 2],
    "Stop duration only (1)": [3],
    "Route deviation only (2)": [4, 5],
    "Speed + Stop (4)": [0, 1, 2, 3],
    "All features (7)": [0, 1, 2, 3, 4, 5, 6],
}


def _summarize(values: list[float]) -> dict[str, float]:
    arr = np.asarray(values, dtype=np.float64)
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    ci95 = 1.96 * std / math.sqrt(len(arr)) if len(arr) > 0 else 0.0
    return {
        "mean": round(mean, 4),
        "std": round(std, 4),
        "ci95": round(ci95, 4),
    }


def run_multi_seed_eval() -> list[dict[str, Any]]:
    per_model: dict[str, list[dict[str, float]]] = {
        "Rule-Based": [],
        "Local Outlier Factor (LOF)": [],
        "Isolation Forest": [],
        "Geo-fencing + Isolation Forest": [],
    }

    for s in SEEDS:
        train_data = generate_dataset(n_trajectories=400, seed=s * 10 + 1, gps_noise_m=3.5)
        val_data = generate_dataset(n_trajectories=150, seed=s * 10 + 2, gps_noise_m=3.5)
        test_data = generate_dataset(n_trajectories=300, seed=s * 10 + 3, gps_noise_m=3.5)

        train_norm = [t for t in train_data if not t.is_anomalous]
        X_train_norm, _, _ = _featurize(train_norm)
        X_val, y_val, ctx_val = _featurize(val_data)
        X_test, y_test, ctx_test = _featurize(test_data)

        detectors = [
            (RuleBasedDetector().fit(X_train_norm, X_val, y_val), False),
            (LOFDetector(n_neighbors=20, contamination=0.08).fit(X_train_norm, X_val, y_val), False),
            (IsolationForestDetector(n_estimators=200, contamination=0.08, random_state=s).fit(X_train_norm, X_val, y_val), False),
            (HybridGeofenceIFDetector(n_estimators=200, contamination=0.08, random_state=s).fit(X_train_norm, X_val, y_val, ctx_val), True),
        ]

        for det, use_ctx in detectors:
            scores = det.score(X_test, ctx_test) if use_ctx else det.score(X_test)
            preds = det.predict(X_test, ctx_test) if use_ctx else det.predict(X_test)
            m = _classification_metrics(y_test, preds, scores)
            m["detection_delay_s"] = _compute_detection_delay_s(test_data, det, use_zone_ctx=use_ctx)
            per_model[det.name].append(m)

    summary: list[dict[str, Any]] = []
    metric_keys = ["precision", "recall", "f1_score", "fpr", "auc", "false_alerts_per_hour", "detection_delay_s"]
    for model_name, rows in per_model.items():
        entry: dict[str, Any] = {"model": model_name, "n_seeds": len(rows)}
        for k in metric_keys:
            entry[k] = _summarize([float(r[k]) for r in rows])
        summary.append(entry)
    return summary


def run_feature_ablation() -> list[dict[str, Any]]:
    records: dict[tuple[str, str], list[dict[str, float]]] = {}
    for subset_name in FEATURE_SUBSETS:
        for model_label in ("Isolation Forest", "LOF"):
            records[(model_label, subset_name)] = []

    for s in SEEDS:
        train_data = generate_dataset(n_trajectories=400, seed=s * 10 + 1, gps_noise_m=3.5)
        val_data = generate_dataset(n_trajectories=150, seed=s * 10 + 2, gps_noise_m=3.5)
        test_data = generate_dataset(n_trajectories=300, seed=s * 10 + 3, gps_noise_m=3.5)

        train_norm = [t for t in train_data if not t.is_anomalous]
        X_train_norm, _, _ = _featurize(train_norm)
        X_val, y_val, _ = _featurize(val_data)
        X_test, y_test, _ = _featurize(test_data)

        for subset_name, cols in FEATURE_SUBSETS.items():
            Xtr = X_train_norm[:, cols]
            Xva = X_val[:, cols]
            Xte = X_test[:, cols]

            iforest = IsolationForestDetector(
                n_estimators=200, contamination=0.08, random_state=s
            ).fit(Xtr, Xva, y_val)
            m_if = _classification_metrics(y_test, iforest.predict(Xte), iforest.score(Xte))
            records[("Isolation Forest", subset_name)].append(m_if)

            lof = LOFDetector(n_neighbors=20, contamination=0.08).fit(Xtr, Xva, y_val)
            m_lof = _classification_metrics(y_test, lof.predict(Xte), lof.score(Xte))
            records[("LOF", subset_name)].append(m_lof)

    summary: list[dict[str, Any]] = []
    for subset_name in FEATURE_SUBSETS:
        for model_label in ("Isolation Forest", "LOF"):
            rows = records[(model_label, subset_name)]
            summary.append(
                {
                    "model": model_label,
                    "feature_subset": subset_name,
                    "n_seeds": len(rows),
                    "precision": _summarize([float(r["precision"]) for r in rows]),
                    "recall": _summarize([float(r["recall"]) for r in rows]),
                    "f1_score": _summarize([float(r["f1_score"]) for r in rows]),
                    "auc": _summarize([float(r["auc"]) for r in rows]),
                    "false_alerts_per_hour": _summarize([float(r["false_alerts_per_hour"]) for r in rows]),
                }
            )
    return summary


def main() -> None:
    out_dir = Path(__file__).resolve().parent / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    multi_seed = run_multi_seed_eval()
    ablation = run_feature_ablation()

    payload = {
        "seeds": SEEDS,
        "trajectories_per_seed": {"train": 400, "val": 150, "test": 300, "gps_noise_m": 3.5},
        "multi_seed_model_comparison": multi_seed,
        "feature_ablation": ablation,
    }
    (out_dir / "ablation_ci_results.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    lines = [
        "# Multi-Seed (10 Seeds) & Feature Ablation Results",
        "",
        "## 1. 10-Seed Model Comparison (Mean ± 95% CI, 300 Test Trajectories/Seed)",
        "",
        "| Model | Precision | Recall | F1-Score | AUC | False Alerts/hr | Delay (s) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in multi_seed:
        lines.append(
            f"| {r['model']} | {r['precision']['mean']:.4f} ± {r['precision']['ci95']:.4f} | "
            f"{r['recall']['mean']:.4f} ± {r['recall']['ci95']:.4f} | "
            f"{r['f1_score']['mean']:.4f} ± {r['f1_score']['ci95']:.4f} | "
            f"{r['auc']['mean']:.4f} ± {r['auc']['ci95']:.4f} | "
            f"{r['false_alerts_per_hour']['mean']:.2f} ± {r['false_alerts_per_hour']['ci95']:.2f} | "
            f"{r['detection_delay_s']['mean']:.2f} ± {r['detection_delay_s']['ci95']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## 2. Feature Ablation (Mean ± 95% CI across 10 Seeds)",
            "",
            "| Model | Feature Subset | Precision | Recall | F1-Score | AUC | False Alerts/hr |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for r in ablation:
        lines.append(
            f"| {r['model']} | {r['feature_subset']} | "
            f"{r['precision']['mean']:.4f} ± {r['precision']['ci95']:.4f} | "
            f"{r['recall']['mean']:.4f} ± {r['recall']['ci95']:.4f} | "
            f"{r['f1_score']['mean']:.4f} ± {r['f1_score']['ci95']:.4f} | "
            f"{r['auc']['mean']:.4f} ± {r['auc']['ci95']:.4f} | "
            f"{r['false_alerts_per_hour']['mean']:.2f} ± {r['false_alerts_per_hour']['ci95']:.2f} |"
        )

    (out_dir / "ablation_ci_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Saved ablation_ci_results.json and ablation_ci_report.md")


if __name__ == "__main__":
    main()
