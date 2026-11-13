# Phase 1 Experimental Results (Simulated Trajectories & Permissioned Ledger)

## Experiment A — AI Model Comparison (Held-out Test Set: 300 Trajectories)

| Model | Precision | Recall | F1-Score | FPR | AUC | False Alerts/hr | Detection Delay (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Rule-Based | 0.3288 | 1.0000 | 0.4948 | 0.6447 | 0.7950 | 19.34 | 11.53 |
| Local Outlier Factor (LOF) | 0.9730 | 1.0000 | 0.9863 | 0.0088 | 1.0000 | 0.26 | 5.07 |
| Isolation Forest | 0.9730 | 1.0000 | 0.9863 | 0.0088 | 0.9967 | 0.26 | 6.11 |
| Geo-fencing + Isolation Forest | 0.9722 | 0.9722 | 0.9722 | 0.0088 | 0.9967 | 0.26 | 6.25 |

## Experiment B — GPS Accuracy & Reliability (Geo-fencing + Isolation Forest)

| GPS Condition | Missed Detections (FN) | False Alerts (FP) | Precision | Recall | F1-Score | False Alerts/hr |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2m GPS error | 0 | 21 | 0.7000 | 1.0000 | 0.8235 | 4.17 |
| 5m GPS error | 11 | 4 | 0.9048 | 0.7755 | 0.8352 | 0.79 |
| 10m GPS error | 14 | 53 | 0.4045 | 0.7200 | 0.5180 | 10.60 |
| 15m GPS error | 0 | 143 | 0.2513 | 1.0000 | 0.4017 | 28.22 |
| Missing GPS readings (30% dropout) | 0 | 1 | 0.9821 | 1.0000 | 0.9910 | 0.21 |
| Sudden GPS jumps (15% spike) | 0 | 150 | 0.2424 | 1.0000 | 0.3902 | 29.61 |

## Experiment C — Digital Identity Security (100 trials per case)

- Average Issuance + Ledger Anchor Latency: **0.4064 ms**
- Ledger Blocks: **202** (Chain Intact: **True**)

| Test Case | Total | Accepted | Rejected | Avg Verification Latency (ms) |
| --- | ---: | ---: | ---: | ---: |
| valid | 100 | 100 | 0 | 0.3484 |
| modified | 100 | 0 | 100 | 0.4302 |
| expired | 100 | 0 | 100 | 0.3964 |
| revoked | 100 | 0 | 100 | 0.3415 |
| invalid_issuer_signature | 100 | 0 | 100 | 0.3825 |
| replayed | 100 | 0 | 100 | 0.4303 |
