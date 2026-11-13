"""Reproducible IEEE Evaluation Suite (Phase 1 Core Engine).

Executes:
- Experiment A: AI Model Comparison (Rule-based, LOF, Isolation Forest,
  Geo-fencing + Isolation Forest) on trajectory-split test data.
- Experiment B: GPS Accuracy & Reliability (2m, 5m, 10m, 15m noise,
  missing GPS readings, sudden GPS jumps).
- Experiment C: Digital Identity Security (valid, modified, expired,
  revoked, invalid issuer signature, replayed credential + latency).

All results are saved to experiments/results/phase1_results.json and
experiments/results/phase1_report.md.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import roc_auc_score

from tourist_safety.anomaly import (
    HybridGeofenceIFDetector,
    IsolationForestDetector,
    LOFDetector,
    RuleBasedDetector,
    extract_window_features,
)
from tourist_safety.identity import (
    CredentialIssuer,
    CredentialVerifier,
    PermissionedIdentityLedger,
)
from tourist_safety.simulator import TrajectoryScenario, generate_dataset


def _featurize(
    trajectories: list[TrajectoryScenario],
) -> tuple[np.ndarray, np.ndarray, list[tuple]]:
    X = np.vstack(
        [
            extract_window_features(t.observations, t.planned_route).to_vector()
            for t in trajectories
        ]
    )
    y = np.array([int(t.is_anomalous) for t in trajectories], dtype=int)
    ctxs = [t.zone_context for t in trajectories]
    return X, y, ctxs


def _compute_detection_delay_s(
    trajectories: list[TrajectoryScenario],
    detector: Any,
    use_zone_ctx: bool = False,
) -> float:
    """Mean seconds from anomaly onset to first positive window detection."""
    delays: list[float] = []
    for t in trajectories:
        if not t.is_anomalous or t.anomaly_onset_index is None:
            continue
        obs = t.observations
        onset_idx = t.anomaly_onset_index
        if onset_idx >= len(obs):
            continue
        onset_time = obs[onset_idx].timestamp
        detected_time = None
        # Evaluate expanding prefix from onset_idx + 1 onward
        for end_idx in range(max(2, onset_idx + 2), len(obs) + 1):
            feats = extract_window_features(obs[:end_idx], t.planned_route).to_vector().reshape(1, -1)
            if use_zone_ctx:
                pred = int(detector.predict(feats, [t.zone_context])[0])
            else:
                pred = int(detector.predict(feats)[0])
            if pred == 1:
                detected_time = obs[end_idx - 1].timestamp
                break
        if detected_time is not None:
            delays.append(max(0.0, (detected_time - onset_time).total_seconds()))
    return round(float(np.mean(delays)), 2) if delays else float("nan")


def _classification_metrics(
    y_true: np.ndarray, y_pred: np.ndarray, y_score: np.ndarray
) -> dict[str, float]:
    tp = int(np.sum((y_pred == 1) & (y_true == 1)))
    fp = int(np.sum((y_pred == 1) & (y_true == 0)))
    fn = int(np.sum((y_pred == 0) & (y_true == 1)))
    tn = int(np.sum((y_pred == 0) & (y_true == 0)))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    auc = float(roc_auc_score(y_true, y_score)) if len(np.unique(y_true)) > 1 else 0.0

    # Each trajectory is 120s (2 minutes). False alerts per simulated tourist-hour:
    total_normal_hours = (np.sum(y_true == 0) * 120.0) / 3600.0
    false_alerts_per_hr = fp / total_normal_hours if total_normal_hours > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "fpr": round(fpr, 4),
        "auc": round(auc, 4),
        "false_alerts_per_hour": round(false_alerts_per_hr, 2),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


def run_experiment_a(
    train_data: list[TrajectoryScenario],
    val_data: list[TrajectoryScenario],
    test_data: list[TrajectoryScenario],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Experiment A: AI Model Comparison on identical trajectory-split partitions."""
    train_norm = [t for t in train_data if not t.is_anomalous]
    X_train_norm, _, _ = _featurize(train_norm)
    X_val, y_val, ctx_val = _featurize(val_data)
    X_test, y_test, ctx_test = _featurize(test_data)

    rule = RuleBasedDetector().fit(X_train_norm, X_val, y_val)
    lof = LOFDetector(n_neighbors=20, contamination=0.08).fit(X_train_norm, X_val, y_val)
    iforest = IsolationForestDetector(
        n_estimators=200, contamination=0.08, random_state=42
    ).fit(X_train_norm, X_val, y_val)
    hybrid = HybridGeofenceIFDetector(
        n_estimators=200, contamination=0.08, random_state=42
    ).fit(X_train_norm, X_val, y_val, ctx_val)

    results: list[dict[str, Any]] = []
    for det, use_ctx in [
        (rule, False),
        (lof, False),
        (iforest, False),
        (hybrid, True),
    ]:
        scores = det.score(X_test, ctx_test) if use_ctx else det.score(X_test)
        preds = det.predict(X_test, ctx_test) if use_ctx else det.predict(X_test)
        metrics = _classification_metrics(y_test, preds, scores)
        metrics["model"] = det.name
        metrics["detection_delay_s"] = _compute_detection_delay_s(
            test_data, det, use_zone_ctx=use_ctx
        )
        results.append(metrics)

    models = {"rule": rule, "lof": lof, "iforest": iforest, "hybrid": hybrid}
    return results, models


def run_experiment_b(hybrid_model: HybridGeofenceIFDetector) -> list[dict[str, Any]]:
    """Experiment B: GPS Accuracy & Reliability stress tests."""
    conditions = [
        {"condition": "2m GPS error", "gps_noise_m": 2.0, "dropout_prob": 0.0, "jump_prob": 0.0, "seed": 501},
        {"condition": "5m GPS error", "gps_noise_m": 5.0, "dropout_prob": 0.0, "jump_prob": 0.0, "seed": 502},
        {"condition": "10m GPS error", "gps_noise_m": 10.0, "dropout_prob": 0.0, "jump_prob": 0.0, "seed": 503},
        {"condition": "15m GPS error", "gps_noise_m": 15.0, "dropout_prob": 0.0, "jump_prob": 0.0, "seed": 504},
        {"condition": "Missing GPS readings (30% dropout)", "gps_noise_m": 3.0, "dropout_prob": 0.30, "jump_prob": 0.0, "seed": 505},
        {"condition": "Sudden GPS jumps (15% spike)", "gps_noise_m": 3.0, "dropout_prob": 0.0, "jump_prob": 0.15, "seed": 506},
    ]
    rows: list[dict[str, Any]] = []
    for cfg in conditions:
        ds = generate_dataset(
            n_trajectories=200,
            seed=cfg["seed"],
            gps_noise_m=cfg["gps_noise_m"],
            dropout_prob=cfg["dropout_prob"],
            jump_prob=cfg["jump_prob"],
        )
        X, y_true, ctxs = _featurize(ds)
        scores = hybrid_model.score(X, ctxs)
        preds = hybrid_model.predict(X, ctxs)
        m = _classification_metrics(y_true, preds, scores)
        rows.append(
            {
                "condition": cfg["condition"],
                "missed_detections_fn": m["fn"],
                "false_alerts_fp": m["fp"],
                "precision": m["precision"],
                "recall": m["recall"],
                "f1_score": m["f1_score"],
                "false_alerts_per_hour": m["false_alerts_per_hour"],
            }
        )
    return rows


def run_experiment_c(n_trials: int = 100) -> dict[str, Any]:
    """Experiment C: Digital Identity Security & Ledger Latency."""
    from datetime import datetime, timedelta, timezone

    ledger = PermissionedIdentityLedger()
    issuer = CredentialIssuer("did:tourist:authority:in-tn-01")
    issuer.register_on_ledger(ledger)
    verifier = CredentialVerifier(ledger)
    rogue_issuer = CredentialIssuer("did:tourist:authority:rogue")

    base_now = datetime(2026, 11, 12, 9, 0, 0, tzinfo=timezone.utc)
    issue_latencies_ms: list[float] = []

    cases = {
        "valid": {"total": 0, "accepted": 0, "rejected": 0, "latencies_ms": []},
        "modified": {"total": 0, "accepted": 0, "rejected": 0, "latencies_ms": []},
        "expired": {"total": 0, "accepted": 0, "rejected": 0, "latencies_ms": []},
        "revoked": {"total": 0, "accepted": 0, "rejected": 0, "latencies_ms": []},
        "invalid_issuer_signature": {"total": 0, "accepted": 0, "rejected": 0, "latencies_ms": []},
        "replayed": {"total": 0, "accepted": 0, "rejected": 0, "latencies_ms": []},
    }

    for i in range(n_trials):
        t0 = time.perf_counter()
        vc = issuer.issue_credential(
            ledger=ledger,
            full_name=f"Tourist {i}",
            nationality="IN",
            passport_or_id_number=f"P{100000 + i}",
            emergency_contact_name="Emergency Contact",
            emergency_contact_phone="+91-9876543210",
            validity_days=15,
            now=base_now,
        )
        issue_latencies_ms.append((time.perf_counter() - t0) * 1000.0)

        # 1. Valid
        r_valid = verifier.verify(vc, presentation_nonce=f"n-valid-{i}", now=base_now + timedelta(hours=1))
        cases["valid"]["total"] += 1
        cases["valid"]["accepted" if r_valid.valid else "rejected"] += 1
        cases["valid"]["latencies_ms"].append(r_valid.latency_ms)

        # 2. Modified
        tampered = vc.model_copy(deep=True)
        tampered.credential_subject.full_name = "Tampered Name"
        r_mod = verifier.verify(tampered, presentation_nonce=f"n-mod-{i}", now=base_now)
        cases["modified"]["total"] += 1
        cases["modified"]["accepted" if r_mod.valid else "rejected"] += 1
        cases["modified"]["latencies_ms"].append(r_mod.latency_ms)

        # 3. Expired
        r_exp = verifier.verify(vc, presentation_nonce=f"n-exp-{i}", now=base_now + timedelta(days=20))
        cases["expired"]["total"] += 1
        cases["expired"]["accepted" if r_exp.valid else "rejected"] += 1
        cases["expired"]["latencies_ms"].append(r_exp.latency_ms)

        # 4. Invalid issuer signature
        forged = vc.model_copy(deep=True)
        forged.proof_signature_b64 = rogue_issuer.issue_credential(
            ledger=PermissionedIdentityLedger(),
            full_name="Rogue",
            nationality="XX",
            passport_or_id_number="X000",
            emergency_contact_name="X",
            emergency_contact_phone="0",
            now=base_now,
        ).proof_signature_b64
        r_sig = verifier.verify(forged, presentation_nonce=f"n-sig-{i}", now=base_now)
        cases["invalid_issuer_signature"]["total"] += 1
        cases["invalid_issuer_signature"]["accepted" if r_sig.valid else "rejected"] += 1
        cases["invalid_issuer_signature"]["latencies_ms"].append(r_sig.latency_ms)

        # 5. Replayed (reuse n-valid-{i})
        r_rep = verifier.verify(vc, presentation_nonce=f"n-valid-{i}", now=base_now + timedelta(minutes=5))
        cases["replayed"]["total"] += 1
        cases["replayed"]["accepted" if r_rep.valid else "rejected"] += 1
        cases["replayed"]["latencies_ms"].append(r_rep.latency_ms)

        # 6. Revoked
        ledger.revoke_credential(vc.credential_id, reason="test_revocation")
        r_rev = verifier.verify(vc, presentation_nonce=f"n-rev-{i}", now=base_now)
        cases["revoked"]["total"] += 1
        cases["revoked"]["accepted" if r_rev.valid else "rejected"] += 1
        cases["revoked"]["latencies_ms"].append(r_rev.latency_ms)

    summary_rows = []
    for name, c in cases.items():
        summary_rows.append(
            {
                "test_case": name,
                "total": c["total"],
                "accepted": c["accepted"],
                "rejected": c["rejected"],
                "avg_latency_ms": round(float(np.mean(c["latencies_ms"])), 4),
            }
        )

    return {
        "n_trials": n_trials,
        "avg_issuance_anchor_latency_ms": round(float(np.mean(issue_latencies_ms)), 4),
        "ledger_block_count": ledger.block_count(),
        "ledger_chain_intact": ledger.chain_is_intact(),
        "cases": summary_rows,
    }


def main() -> None:
    out_dir = Path(__file__).resolve().parent / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Trajectory-level split (no window leakage across train/val/test)
    # Train/val include realistic 2-5m GPS noise so detectors tolerate normal jitter
    train_data = generate_dataset(n_trajectories=400, seed=42, gps_noise_m=3.5)
    val_data = generate_dataset(n_trajectories=150, seed=108, gps_noise_m=3.5)
    test_data = generate_dataset(n_trajectories=300, seed=999, gps_noise_m=3.5)

    exp_a, models = run_experiment_a(train_data, val_data, test_data)
    exp_b = run_experiment_b(models["hybrid"])
    exp_c = run_experiment_c(n_trials=100)

    payload = {
        "dataset_info": {
            "train_trajectories": len(train_data),
            "val_trajectories": len(val_data),
            "test_trajectories": len(test_data),
            "split_policy": "trajectory_level_independent_seeds",
        },
        "experiment_a_model_comparison": exp_a,
        "experiment_b_gps_sensitivity": exp_b,
        "experiment_c_identity_security": exp_c,
    }

    (out_dir / "phase1_results.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    md_lines = [
        "# Phase 1 Experimental Results (Simulated Trajectories & Permissioned Ledger)",
        "",
        "## Experiment A — AI Model Comparison (Held-out Test Set: 300 Trajectories)",
        "",
        "| Model | Precision | Recall | F1-Score | FPR | AUC | False Alerts/hr | Detection Delay (s) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in exp_a:
        md_lines.append(
            f"| {r['model']} | {r['precision']:.4f} | {r['recall']:.4f} | {r['f1_score']:.4f} | "
            f"{r['fpr']:.4f} | {r['auc']:.4f} | {r['false_alerts_per_hour']:.2f} | {r['detection_delay_s']} |"
        )

    md_lines.extend(
        [
            "",
            "## Experiment B — GPS Accuracy & Reliability (Geo-fencing + Isolation Forest)",
            "",
            "| GPS Condition | Missed Detections (FN) | False Alerts (FP) | Precision | Recall | F1-Score | False Alerts/hr |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for r in exp_b:
        md_lines.append(
            f"| {r['condition']} | {r['missed_detections_fn']} | {r['false_alerts_fp']} | "
            f"{r['precision']:.4f} | {r['recall']:.4f} | {r['f1_score']:.4f} | {r['false_alerts_per_hour']:.2f} |"
        )

    md_lines.extend(
        [
            "",
            f"## Experiment C — Digital Identity Security ({exp_c['n_trials']} trials per case)",
            "",
            f"- Average Issuance + Ledger Anchor Latency: **{exp_c['avg_issuance_anchor_latency_ms']} ms**",
            f"- Ledger Blocks: **{exp_c['ledger_block_count']}** (Chain Intact: **{exp_c['ledger_chain_intact']}**)",
            "",
            "| Test Case | Total | Accepted | Rejected | Avg Verification Latency (ms) |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for r in exp_c["cases"]:
        md_lines.append(
            f"| {r['test_case']} | {r['total']} | {r['accepted']} | {r['rejected']} | {r['avg_latency_ms']:.4f} |"
        )

    (out_dir / "phase1_report.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print("\n".join(md_lines))


if __name__ == "__main__":
    main()
