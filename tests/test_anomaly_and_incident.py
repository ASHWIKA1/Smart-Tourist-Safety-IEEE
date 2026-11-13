"""Unit tests for AI anomaly detectors and end-to-end incident workflow."""

from datetime import datetime, timedelta, timezone

import numpy as np

from tourist_safety.anomaly import (
    HybridGeofenceIFDetector,
    IsolationForestDetector,
    LOFDetector,
    RuleBasedDetector,
    extract_window_features,
)
from tourist_safety.geofence import GeoFenceEngine
from tourist_safety.incident import IncidentManager
from tourist_safety.models import IncidentStatus
from tourist_safety.simulator import default_test_geography, generate_dataset


def test_models_fit_and_predict_without_leakage():
    train_data = generate_dataset(n_trajectories=120, seed=101)
    test_data = generate_dataset(n_trajectories=60, seed=202)

    X_train_norm = np.vstack(
        [
            extract_window_features(t.observations, t.planned_route).to_vector()
            for t in train_data
            if not t.is_anomalous
        ]
    )
    X_val = np.vstack(
        [
            extract_window_features(t.observations, t.planned_route).to_vector()
            for t in train_data
        ]
    )
    y_val = np.array([int(t.is_anomalous) for t in train_data])
    ctx_val = [t.zone_context for t in train_data]

    X_test = np.vstack(
        [
            extract_window_features(t.observations, t.planned_route).to_vector()
            for t in test_data
        ]
    )
    ctx_test = [t.zone_context for t in test_data]

    for det in [
        RuleBasedDetector().fit(X_train_norm, X_val, y_val),
        LOFDetector().fit(X_train_norm, X_val, y_val),
        IsolationForestDetector().fit(X_train_norm, X_val, y_val),
    ]:
        preds = det.predict(X_test)
        assert preds.shape == (len(test_data),)

    hybrid = HybridGeofenceIFDetector().fit(X_train_norm, X_val, y_val, ctx_val)
    h_preds = hybrid.predict(X_test, ctx_test)
    assert h_preds.shape == (len(test_data),)


def test_incident_lifecycle_restricted_entry():
    zones, route = default_test_geography()
    train_data = generate_dataset(n_trajectories=80, seed=7)
    X_train_norm = np.vstack(
        [
            extract_window_features(t.observations, t.planned_route).to_vector()
            for t in train_data
            if not t.is_anomalous
        ]
    )
    hybrid = HybridGeofenceIFDetector().fit(X_train_norm)
    manager = IncidentManager(GeoFenceEngine(zones), hybrid)

    restricted_traj = next(
        t for t in generate_dataset(n_trajectories=80, seed=9)
        if t.scenario_type == "restricted_entry"
    )
    alert = manager.process_window(restricted_traj.observations, route)
    assert alert is not None
    assert alert.status == IncidentStatus.PENDING
    assert "restricted_zone_entry" in alert.reason

    t_ack = datetime.now(timezone.utc)
    manager.update_status(alert.alert_id, IncidentStatus.ACKNOWLEDGED, at=t_ack)
    manager.update_status(
        alert.alert_id,
        IncidentStatus.RESOLVED,
        at=t_ack + timedelta(seconds=5),
    )
    assert manager.alerts[alert.alert_id].status == IncidentStatus.RESOLVED
