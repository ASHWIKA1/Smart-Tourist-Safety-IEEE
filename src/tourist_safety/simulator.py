"""Reproducible synthetic tourist trajectory generator.

Generates labelled tourist trajectories partitioned by tourist/journey
(preventing window leakage across train/val/test splits as required in
Section VII of the paper). Supports controlled GPS noise, missing readings,
sudden GPS jumps, sightseeing stops in safe zones, and genuine anomalies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np

from .geofence import EARTH_RADIUS_M, GeoFenceEngine, evaluate_zone
from .models import GeoPoint, GeoZone, GPSObservation, ZoneCategory, ZoneState


@dataclass
class TrajectoryScenario:
    trajectory_id: str
    tourist_id: str
    scenario_type: str  # normal, sightseeing_safe, off_route_stop, erratic_speed, restricted_entry
    is_anomalous: bool
    observations: list[GPSObservation]
    planned_route: list[GeoPoint]
    zone_context: tuple[Optional[ZoneCategory], ZoneState]
    anomaly_onset_index: Optional[int] = None


def default_test_geography() -> tuple[list[GeoZone], list[GeoPoint]]:
    """Create a realistic tourist park / heritage corridor geography."""
    origin_lat, origin_lon = 11.3610, 77.8280
    planned_route = [
        _offset_point(origin_lat, origin_lon, dx_m=0.0, dy_m=0.0),
        _offset_point(origin_lat, origin_lon, dx_m=300.0, dy_m=150.0),
        _offset_point(origin_lat, origin_lon, dx_m=650.0, dy_m=220.0),
        _offset_point(origin_lat, origin_lon, dx_m=1000.0, dy_m=300.0),
    ]
    zones = [
        GeoZone(
            zone_id="zone-safe-plaza",
            name="Heritage Plaza (Safe)",
            category=ZoneCategory.SAFE,
            center=_offset_point(origin_lat, origin_lon, dx_m=300.0, dy_m=150.0),
            radius_m=160.0,
            buffer_m=20.0,
        ),
        GeoZone(
            zone_id="zone-caution-trail",
            name="Steep Trail (Caution)",
            category=ZoneCategory.CAUTION,
            center=_offset_point(origin_lat, origin_lon, dx_m=680.0, dy_m=240.0),
            radius_m=120.0,
            buffer_m=25.0,
        ),
        GeoZone(
            zone_id="zone-restricted-cliff",
            name="Cliff Hazard Area (Restricted)",
            category=ZoneCategory.RESTRICTED,
            center=_offset_point(origin_lat, origin_lon, dx_m=680.0, dy_m=470.0),
            radius_m=90.0,
            buffer_m=30.0,
        ),
    ]
    return zones, planned_route


def _offset_point(lat: float, lon: float, dx_m: float, dy_m: float) -> GeoPoint:
    dlat = math.degrees(dy_m / EARTH_RADIUS_M)
    dlon = math.degrees(dx_m / (EARTH_RADIUS_M * math.cos(math.radians(lat))))
    return GeoPoint(lat=lat + dlat, lon=lon + dlon)


def _interpolate_route(route: list[GeoPoint], frac: float) -> GeoPoint:
    frac = max(0.0, min(1.0, frac))
    idx_f = frac * (len(route) - 1)
    idx = min(int(idx_f), len(route) - 2)
    local_t = idx_f - idx
    p0, p1 = route[idx], route[idx + 1]
    return GeoPoint(
        lat=p0.lat + (p1.lat - p0.lat) * local_t,
        lon=p0.lon + (p1.lon - p0.lon) * local_t,
    )


def generate_trajectory(
    trajectory_id: str,
    tourist_id: str,
    scenario_type: str,
    zones: list[GeoZone],
    planned_route: list[GeoPoint],
    rng: np.random.Generator,
    n_points: int = 24,
    interval_s: float = 5.0,
    gps_noise_m: float = 2.0,
    dropout_prob: float = 0.0,
    jump_prob: float = 0.0,
) -> TrajectoryScenario:
    """Generate one synthetic trajectory window with controlled GPS conditions."""
    base_time = datetime(2026, 11, 12, 9, 0, 0, tzinfo=timezone.utc)
    obs_list: list[GPSObservation] = []
    onset_idx: Optional[int] = None
    is_anomalous = scenario_type in {"off_route_stop", "erratic_speed", "restricted_entry"}

    for i in range(n_points):
        if dropout_prob > 0 and 0 < i < n_points - 1 and rng.random() < dropout_prob:
            continue

        t = base_time + timedelta(seconds=i * interval_s)
        progress = i / max(1, n_points - 1)

        if scenario_type == "normal":
            # Steady pedestrian walking (~1.2-1.6 m/s) along planned route
            base_pt = _interpolate_route(planned_route, 0.08 + 0.17 * progress)
            # Mild natural wandering (+/- 12 m)
            base_pt = _offset_point(
                base_pt.lat,
                base_pt.lon,
                dx_m=float(rng.normal(0.0, 5.0)),
                dy_m=float(rng.normal(0.0, 8.0)),
            )
        elif scenario_type == "sightseeing_safe":
            # Normal walk then pauses at Heritage Plaza (Safe zone) to sightsee
            if i < 6:
                base_pt = _interpolate_route(planned_route, 0.24 + 0.015 * i)
            elif i < 18:
                base_pt = _interpolate_route(planned_route, 0.33)
            else:
                base_pt = _interpolate_route(planned_route, 0.33 + 0.015 * (i - 18))
        elif scenario_type == "off_route_stop":
            # Walks on route, then drifts 70-130 m off-route and stops
            if i < 6:
                base_pt = _interpolate_route(planned_route, 0.25 + 0.015 * i)
            else:
                if onset_idx is None:
                    onset_idx = len(obs_list)
                anchor = _interpolate_route(planned_route, 0.34)
                drift = min(1.0, (i - 5) / 6.0)
                base_pt = _offset_point(anchor.lat, anchor.lon, dx_m=15.0 * drift, dy_m=-105.0 * drift)
        elif scenario_type == "erratic_speed":
            # Sudden high-speed burst + zigzag off route
            if i < 7:
                base_pt = _interpolate_route(planned_route, 0.2 + 0.015 * i)
            else:
                if onset_idx is None:
                    onset_idx = len(obs_list)
                anchor = _interpolate_route(planned_route, 0.30)
                step = i - 7
                base_pt = _offset_point(
                    anchor.lat,
                    anchor.lon,
                    dx_m=28.0 * step,
                    dy_m=45.0 * math.sin(step * 1.4),
                )
        elif scenario_type == "restricted_entry":
            # Leaves route northward into the restricted cliff hazard zone
            if i < 6:
                base_pt = _interpolate_route(planned_route, 0.45 + 0.015 * i)
            else:
                if onset_idx is None:
                    onset_idx = len(obs_list)
                anchor = _interpolate_route(planned_route, 0.54)
                frac_in = min(1.0, (i - 5) / 8.0)
                base_pt = _offset_point(anchor.lat, anchor.lon, dx_m=100.0 * frac_in, dy_m=265.0 * frac_in)
        else:
            raise ValueError(f"Unknown scenario_type: {scenario_type}")

        # Add Gaussian GPS noise
        dx_noise = float(rng.normal(0.0, gps_noise_m / math.sqrt(2.0)))
        dy_noise = float(rng.normal(0.0, gps_noise_m / math.sqrt(2.0)))

        # Optional sudden GPS jump spike
        if jump_prob > 0 and rng.random() < jump_prob:
            dx_noise += float(rng.choice([-1.0, 1.0]) * rng.uniform(60.0, 110.0))
            dy_noise += float(rng.choice([-1.0, 1.0]) * rng.uniform(60.0, 110.0))

        noisy_pt = _offset_point(base_pt.lat, base_pt.lon, dx_noise, dy_noise)
        obs_list.append(
            GPSObservation(
                tourist_id=tourist_id,
                timestamp=t,
                lat=noisy_pt.lat,
                lon=noisy_pt.lon,
                accuracy_m=max(1.5, gps_noise_m * 1.2),
            )
        )

    # Determine dominant zone context from final valid observation
    zone_ctx: tuple[Optional[ZoneCategory], ZoneState] = (None, ZoneState.OUTSIDE)
    if obs_list:
        last_pt = GeoPoint(lat=obs_list[-1].lat, lon=obs_list[-1].lon)
        zone_evals = [evaluate_zone(last_pt, z) for z in zones]
        top = GeoFenceEngine.highest_risk_zone(zone_evals)
        if top is not None:
            zone_ctx = (top.category, top.state)

    return TrajectoryScenario(
        trajectory_id=trajectory_id,
        tourist_id=tourist_id,
        scenario_type=scenario_type,
        is_anomalous=is_anomalous,
        observations=obs_list,
        planned_route=planned_route,
        zone_context=zone_ctx,
        anomaly_onset_index=onset_idx,
    )


def generate_dataset(
    n_trajectories: int = 300,
    seed: int = 42,
    gps_noise_m: float = 2.0,
    dropout_prob: float = 0.0,
    jump_prob: float = 0.0,
) -> list[TrajectoryScenario]:
    """Generate a balanced, reproducible set of independent tourist trajectories."""
    rng = np.random.default_rng(seed)
    zones, route = default_test_geography()

    # ~75% normal (including sightseeing in safe zones), ~25% anomalous
    scenario_choices = [
        ("normal", 0.50),
        ("sightseeing_safe", 0.25),
        ("off_route_stop", 0.10),
        ("erratic_speed", 0.08),
        ("restricted_entry", 0.07),
    ]
    names = [s[0] for s in scenario_choices]
    probs = [s[1] for s in scenario_choices]

    dataset: list[TrajectoryScenario] = []
    for i in range(n_trajectories):
        sc_type = str(rng.choice(names, p=probs))
        dataset.append(
            generate_trajectory(
                trajectory_id=f"traj-{seed}-{i:04d}",
                tourist_id=f"tourist-{seed}-{i:04d}",
                scenario_type=sc_type,
                zones=zones,
                planned_route=route,
                rng=rng,
                gps_noise_m=gps_noise_m,
                dropout_prob=dropout_prob,
                jump_prob=jump_prob,
            )
        )
    return dataset
