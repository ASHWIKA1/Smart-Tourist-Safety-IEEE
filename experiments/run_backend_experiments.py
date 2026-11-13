"""Phase 2 Backend & Experiment D Benchmark Runner.

Measures:
1. Experiment D — Complete Incident Workflow over live HTTP + WebSocket:
   Tourist restricted-zone entry -> GPS ingestion -> Geo-fence & AI evaluation ->
   Incident creation -> WebSocket authority alert delivery -> Acknowledge & Resolve.
2. Backend API response time & concurrent request throughput.
"""

from __future__ import annotations

import json
import statistics
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import uvicorn
from websockets.sync.client import connect as ws_connect

from tourist_safety.api.app import create_app


def _start_test_server(db_path: Path, port: int = 18765):
    app = create_app(database_url=f"sqlite:///{db_path}")
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            r = httpx.get(f"{base_url}/health", timeout=1.0)
            if r.status_code == 200:
                return app, server, thread, base_url
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("Failed to start local FastAPI server.")


def run_experiment_d_and_perf(n_workflows: int = 20, concurrency: int = 10) -> dict:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "bench.db"
        app, server, thread, base_url = _start_test_server(db_path)
        ws_url = base_url.replace("http://", "ws://") + "/ws/authority/alerts"

        try:
            with httpx.Client(base_url=base_url, timeout=10.0) as client:
                # Register authority and tourist
                auth_reg = client.post(
                    "/api/v1/auth/register",
                    json={"email": "authority@bench.local", "password": "Password123!", "role": "authority"},
                ).json()
                auth_headers = {"Authorization": f"Bearer {auth_reg['access_token']}"}

                tourist_reg = client.post(
                    "/api/v1/auth/register",
                    json={
                        "email": "tourist@bench.local",
                        "password": "Password123!",
                        "role": "tourist",
                        "full_name": "Benchmark Tourist",
                        "tracking_consent": True,
                    },
                ).json()
                tourist_headers = {"Authorization": f"Bearer {tourist_reg['access_token']}"}

                zones = client.get("/api/v1/zones", headers=auth_headers).json()
                restricted = next(z for z in zones if z["category"] == "restricted")
                r_lat = restricted["center"]["lat"]
                r_lon = restricted["center"]["lon"]

                # Warm up AI window with 5 normal points outside restricted zone
                t_base = datetime.now(timezone.utc)
                for i in range(5):
                    client.post(
                        "/api/v1/telemetry/gps",
                        json={
                            "lat": 11.3610 + 0.00005 * i,
                            "lon": 77.8280 + 0.00005 * i,
                            "accuracy_m": 3.0,
                            "timestamp": (t_base + timedelta(seconds=i * 5)).isoformat(),
                        },
                        headers=tourist_headers,
                    )

                # --- Experiment D: End-to-end Incident Workflow ---
                detection_to_ws_ms: list[float] = []
                end_to_end_resolve_ms: list[float] = []

                with ws_connect(ws_url) as ws:
                    for i in range(n_workflows):
                        t_start = time.perf_counter()
                        gps_resp = client.post(
                            "/api/v1/telemetry/gps",
                            json={
                                "lat": r_lat,
                                "lon": r_lon,
                                "accuracy_m": 3.0,
                                "timestamp": (t_base + timedelta(seconds=30 + i * 5)).isoformat(),
                            },
                            headers=tourist_headers,
                        )
                        assert gps_resp.status_code == 200
                        incident = gps_resp.json()["incident"]
                        assert incident is not None

                        # Wait for WebSocket notification
                        ws_raw = ws.recv(timeout=5.0)
                        t_ws = time.perf_counter()
                        ws_msg = json.loads(ws_raw)
                        assert ws_msg["event"] == "incident_created"
                        alert_id = ws_msg["incident"]["alert_id"]
                        detection_to_ws_ms.append((t_ws - t_start) * 1000.0)

                        # Authority acknowledges & resolves
                        client.patch(
                            f"/api/v1/incidents/{alert_id}/status",
                            json={"status": "acknowledged"},
                            headers=auth_headers,
                        )
                        ws.recv(timeout=5.0)
                        client.patch(
                            f"/api/v1/incidents/{alert_id}/status",
                            json={"status": "resolved"},
                            headers=auth_headers,
                        )
                        ws.recv(timeout=5.0)
                        t_end = time.perf_counter()
                        end_to_end_resolve_ms.append((t_end - t_start) * 1000.0)

                # --- Backend Concurrency Benchmark ---
                total_requests = 100

                def _send_telemetry(idx: int) -> float:
                    t0 = time.perf_counter()
                    r = httpx.post(
                        f"{base_url}/api/v1/telemetry/gps",
                        json={
                            "lat": 11.3612 + 0.00001 * (idx % 10),
                            "lon": 77.8282 + 0.00001 * (idx % 10),
                            "accuracy_m": 3.5,
                            "timestamp": (t_base + timedelta(seconds=300 + idx)).isoformat(),
                        },
                        headers=tourist_headers,
                        timeout=10.0,
                    )
                    assert r.status_code == 200
                    return (time.perf_counter() - t0) * 1000.0

                t_batch_start = time.perf_counter()
                with ThreadPoolExecutor(max_workers=concurrency) as pool:
                    latencies = list(pool.map(_send_telemetry, range(total_requests)))
                batch_elapsed_s = time.perf_counter() - t_batch_start
                latencies_sorted = sorted(latencies)
                p95_idx = min(len(latencies_sorted) - 1, int(0.95 * len(latencies_sorted)))

                return {
                    "experiment_d": {
                        "workflows_completed": n_workflows,
                        "avg_detection_to_ws_alert_ms": round(statistics.mean(detection_to_ws_ms), 2),
                        "p95_detection_to_ws_alert_ms": round(sorted(detection_to_ws_ms)[int(0.95 * len(detection_to_ws_ms))], 2),
                        "avg_end_to_end_resolve_ms": round(statistics.mean(end_to_end_resolve_ms), 2),
                    },
                    "backend_performance": {
                        "total_requests": total_requests,
                        "concurrency": concurrency,
                        "throughput_rps": round(total_requests / batch_elapsed_s, 2),
                        "mean_api_latency_ms": round(statistics.mean(latencies), 2),
                        "p95_api_latency_ms": round(latencies_sorted[p95_idx], 2),
                    },
                }
        finally:
            server.should_exit = True
            thread.join(timeout=5.0)
            app.state.runtime.engine.dispose()


def main() -> None:
    results = run_experiment_d_and_perf()
    out_dir = Path(__file__).resolve().parent / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "phase2_results.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    exp_d = results["experiment_d"]
    perf = results["backend_performance"]
    report = [
        "# Phase 2 Backend & Experiment D Results",
        "",
        "## Experiment D — Complete Incident Workflow (Live HTTP + WebSocket)",
        f"- Workflows Completed: **{exp_d['workflows_completed']}**",
        f"- Avg Detection-to-WebSocket Notification Delay: **{exp_d['avg_detection_to_ws_alert_ms']} ms**",
        f"- P95 Detection-to-WebSocket Notification Delay: **{exp_d['p95_detection_to_ws_alert_ms']} ms**",
        f"- Avg End-to-End Resolution Cycle Time: **{exp_d['avg_end_to_end_resolve_ms']} ms**",
        "",
        "## Backend Concurrent Telemetry Throughput",
        f"- Total Requests: **{perf['total_requests']}** (Concurrency: **{perf['concurrency']}**)",
        f"- Throughput: **{perf['throughput_rps']} req/s**",
        f"- Mean API Response Time: **{perf['mean_api_latency_ms']} ms**",
        f"- P95 API Response Time: **{perf['p95_api_latency_ms']} ms**",
    ]
    (out_dir / "phase2_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
