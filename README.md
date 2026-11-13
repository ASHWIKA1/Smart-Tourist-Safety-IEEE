# Smart Tourist Safety Monitoring and Incident Response System

Phase 1 Core Engine and Experimental Suite (aligned with the Phase-I IEEE system design).

## Implemented Modules (Phase 1)

- `src/tourist_safety/geofence.py`: Haversine great-circle distance, circular & polygonal geo-fencing with warning buffers (`safe`, `caution`, `restricted`), and stateful entry/exit transition tracking.
- `src/tourist_safety/anomaly.py`: Movement window feature extraction (speed, stop duration, route deviation, missing-gap ratio) plus `RuleBasedDetector`, `LOFDetector`, `IsolationForestDetector` (`a(x) = -score_samples(x)`), and `HybridGeofenceIFDetector`.
- `src/tourist_safety/identity.py`: W3C-inspired DID & Verifiable Credential issuance with Ed25519 digital signatures, canonical JSON + SHA-256 hashing, off-chain PII separation, hash-chained permissioned ledger simulation, revocation, expiry, and replay-nonce checks.
- `src/tourist_safety/incident.py`: End-to-end alert prioritization (`SOS > restricted_zone > movement_anomaly`) and incident lifecycle tracking (`pending -> acknowledged -> in_progress -> resolved`).
- `src/tourist_safety/simulator.py`: Reproducible trajectory-split synthetic tourist movement generator with configurable GPS error, dropouts, and sudden jumps.

## Running Tests & Experiments

```powershell
# Run unit & integration tests
.\.venv\Scripts\python.exe -m pytest -v

# Run Experiments A, B, and C
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe experiments\run_experiments.py
```
