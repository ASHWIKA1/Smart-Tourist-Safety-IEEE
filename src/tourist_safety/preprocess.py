"""GPS prefiltering for noisy / spiky tourist trajectories.

Implements the prefiltering step motivated by Experiment B of the paper:

* ``hampel_filter``  - rolling-median (Hampel) identifier that replaces
  isolated position spikes (e.g. 60-110 m urban-canyon jumps) with the local
  median.
* ``kalman_filter``  - causal constant-velocity Kalman filter with
  chi-square innovation gating; suppresses Gaussian position noise and rejects
  gross outliers while remaining usable on-device in real time.
* ``apply_pipeline`` - applies a named pipeline to a ``TrajectoryScenario`` and
  recomputes the zone context from the *filtered* last position.

All filters work in a local east/north plane (metres) around the first fix.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Callable

import numpy as np

from .geofence import EARTH_RADIUS_M, GeoFenceEngine, evaluate_zone
from .models import GeoPoint, GeoZone, GPSObservation, ZoneCategory, ZoneState
from .simulator import TrajectoryScenario

CHI2_2DOF_99_9 = 13.82  # 99.9% gate for a 2-D innovation


def _to_plane(obs: list[GPSObservation]) -> tuple[np.ndarray, float, float]:
    lat0, lon0 = obs[0].lat, obs[0].lon
    k = EARTH_RADIUS_M * math.cos(math.radians(lat0))
    xy = np.array(
        [
            [math.radians(o.lon - lon0) * k, math.radians(o.lat - lat0) * EARTH_RADIUS_M]
            for o in obs
        ]
    )
    return xy, lat0, lon0


def _from_plane(xy: np.ndarray, lat0: float, lon0: float) -> list[tuple[float, float]]:
    k = EARTH_RADIUS_M * math.cos(math.radians(lat0))
    return [
        (lat0 + math.degrees(y / EARTH_RADIUS_M), lon0 + math.degrees(x / k)) for x, y in xy
    ]


def _rebuild(obs: list[GPSObservation], xy: np.ndarray, lat0: float, lon0: float) -> list[GPSObservation]:
    return [
        o.model_copy(update={"lat": la, "lon": lo})
        for o, (la, lo) in zip(obs, _from_plane(xy, lat0, lon0))
    ]


def hampel_filter(
    obs: list[GPSObservation], half_window: int = 3, n_sigma: float = 3.0, floor_m: float = 15.0
) -> list[GPSObservation]:
    """Replace isolated position outliers with the rolling median."""
    if len(obs) < 3:
        return obs
    xy, lat0, lon0 = _to_plane(obs)
    out = xy.copy()
    n = len(obs)
    for i in range(n):
        lo, hi = max(0, i - half_window), min(n, i + half_window + 1)
        win = xy[lo:hi]
        med = np.median(win, axis=0)
        mad = np.median(np.abs(win - med), axis=0)
        thr = np.maximum(n_sigma * 1.4826 * mad, floor_m)
        if np.any(np.abs(xy[i] - med) > thr):
            out[i] = med
    return _rebuild(obs, out, lat0, lon0)


def kalman_filter(
    obs: list[GPSObservation], accel_sigma: float = 1.0, max_consecutive_rejects: int = 3
) -> list[GPSObservation]:
    """Causal constant-velocity Kalman filter with innovation gating."""
    if len(obs) < 2:
        return obs
    xy, lat0, lon0 = _to_plane(obs)
    H = np.array([[1.0, 0, 0, 0], [0, 1.0, 0, 0]])
    x = np.array([xy[0, 0], xy[0, 1], 0.0, 0.0])
    P = np.diag([obs[0].accuracy_m**2, obs[0].accuracy_m**2, 4.0, 4.0])
    out = [xy[0].copy()]
    rejects = 0
    for i in range(1, len(obs)):
        dt = max(1e-3, (obs[i].timestamp - obs[i - 1].timestamp).total_seconds())
        F = np.eye(4)
        F[0, 2] = F[1, 3] = dt
        q = accel_sigma**2
        G = np.array([[dt**2 / 2, 0], [0, dt**2 / 2], [dt, 0], [0, dt]])
        Q = G @ G.T * q
        x = F @ x
        P = F @ P @ F.T + Q
        R = np.eye(2) * (obs[i].accuracy_m**2)
        nu = xy[i] - H @ x
        S = H @ P @ H.T + R
        d2 = float(nu @ np.linalg.solve(S, nu))
        if d2 > CHI2_2DOF_99_9 and rejects < max_consecutive_rejects:
            rejects += 1  # coast on prediction: treat as gross outlier
        else:
            rejects = 0
            K = P @ H.T @ np.linalg.inv(S)
            x = x + K @ nu
            P = (np.eye(4) - K @ H) @ P
        out.append(x[:2].copy())
    return _rebuild(obs, np.array(out), lat0, lon0)


PIPELINES: dict[str, Callable[[list[GPSObservation]], list[GPSObservation]]] = {
    "raw": lambda o: o,
    "hampel": hampel_filter,
    "kalman": kalman_filter,
    "hampel+kalman": lambda o: kalman_filter(hampel_filter(o)),
}


def apply_pipeline(
    traj: TrajectoryScenario, name: str, zones: list[GeoZone]
) -> TrajectoryScenario:
    """Return a copy of ``traj`` with filtered observations and re-derived zone context."""
    if name == "raw":
        return traj
    obs = PIPELINES[name](sorted(traj.observations, key=lambda o: o.timestamp))
    zone_ctx: tuple[ZoneCategory | None, ZoneState] = (None, ZoneState.OUTSIDE)
    if obs:
        last = GeoPoint(lat=obs[-1].lat, lon=obs[-1].lon)
        top = GeoFenceEngine.highest_risk_zone([evaluate_zone(last, z) for z in zones])
        if top is not None:
            zone_ctx = (top.category, top.state)
    return replace(traj, observations=obs, zone_context=zone_ctx)
