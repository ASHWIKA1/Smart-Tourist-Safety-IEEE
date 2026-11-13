"""Tests for GPS prefiltering (Hampel + gated Kalman)."""

from datetime import datetime, timedelta, timezone

import numpy as np

from tourist_safety.geofence import haversine_distance_m
from tourist_safety.models import GeoPoint, GPSObservation
from tourist_safety.preprocess import apply_pipeline, hampel_filter, kalman_filter
from tourist_safety.simulator import default_test_geography, generate_dataset


def _walk(n=20, spike_at=None):
    t0 = datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc)
    obs = []
    for i in range(n):
        lat = 11.3610 + i * 6e-5  # ~6.7 m per 5 s step
        lon = 77.8280
        if i == spike_at:
            lon += 9e-4  # ~98 m east
        obs.append(GPSObservation(tourist_id="t", timestamp=t0 + timedelta(seconds=5 * i), lat=lat, lon=lon, accuracy_m=4.0))
    return obs


def _err(a, b):
    return haversine_distance_m(GeoPoint(lat=a.lat, lon=a.lon), GeoPoint(lat=b.lat, lon=b.lon))


def test_hampel_removes_isolated_spike():
    clean, spiky = _walk(), _walk(spike_at=10)
    assert _err(spiky[10], clean[10]) > 80
    assert _err(hampel_filter(spiky)[10], clean[10]) < 15


def test_hampel_leaves_clean_walk_unchanged():
    clean = _walk()
    out = hampel_filter(clean)
    assert max(_err(a, b) for a, b in zip(out, clean)) < 1e-6


def test_kalman_gates_spike_and_keeps_length():
    clean, spiky = _walk(), _walk(spike_at=10)
    out = kalman_filter(spiky)
    assert len(out) == len(spiky)
    assert _err(out[10], clean[10]) < 25


def test_apply_pipeline_preserves_labels_and_order():
    zones, _ = default_test_geography()
    for traj in generate_dataset(10, seed=7, gps_noise_m=5.0, jump_prob=0.15):
        out = apply_pipeline(traj, "hampel+kalman", zones)
        assert out.is_anomalous == traj.is_anomalous
        assert len(out.observations) == len(traj.observations)
        ts = [o.timestamp for o in out.observations]
        assert ts == sorted(ts)
