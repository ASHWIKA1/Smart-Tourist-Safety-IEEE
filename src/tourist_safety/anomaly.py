"""Movement feature extraction and AI behavioral anomaly detection.

Implements:
- Windowed movement feature extraction (speed, stop duration, route deviation)
- Rule-based baseline detector
- Local Outlier Factor (LOF) baseline detector
- Isolation Forest detector (paper Eq. 5: a(x) = -score_samples(x))
- Context-aware Hybrid Geo-fence + Isolation Forest detector
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

from .geofence import haversine_distance_m, point_to_polyline_distance_m
from .models import GeoPoint, GPSObservation, ZoneCategory, ZoneState


FEATURE_NAMES = [
    "mean_speed_mps",
    "max_speed_mps",
    "std_speed_mps",
    "stop_duration_s",
    "route_deviation_mean_m",
    "route_deviation_max_m",
    "missing_gap_ratio",
]


@dataclass
class WindowFeatures:
    mean_speed_mps: float
    max_speed_mps: float
    std_speed_mps: float
    stop_duration_s: float
    route_deviation_mean_m: float
    route_deviation_max_m: float
    missing_gap_ratio: float

    def to_vector(self) -> np.ndarray:
        return np.array(
            [
                self.mean_speed_mps,
                self.max_speed_mps,
                self.std_speed_mps,
                self.stop_duration_s,
                self.route_deviation_mean_m,
                self.route_deviation_max_m,
                self.missing_gap_ratio,
            ],
            dtype=np.float64,
        )


def extract_window_features(
    observations: list[GPSObservation],
    planned_route: Optional[list[GeoPoint]] = None,
    stop_displacement_m: float = 3.0,
    expected_interval_s: float = 5.0,
    max_accuracy_m: float = 50.0,
) -> WindowFeatures:
    """Extract movement features from a time-ordered GPS observation window."""
    valid = [o for o in observations if o.accuracy_m <= max_accuracy_m]
    valid.sort(key=lambda o: o.timestamp)

    if len(valid) < 2:
        dev = (
            point_to_polyline_distance_m(
                GeoPoint(lat=valid[0].lat, lon=valid[0].lon), planned_route
            )
            if valid and planned_route
            else 0.0
        )
        return WindowFeatures(
            mean_speed_mps=0.0,
            max_speed_mps=0.0,
            std_speed_mps=0.0,
            stop_duration_s=0.0,
            route_deviation_mean_m=dev,
            route_deviation_max_m=dev,
            missing_gap_ratio=1.0 if len(observations) > 1 else 0.0,
        )

    speeds: list[float] = []
    stop_duration_s = 0.0
    gap_count = 0

    for i in range(1, len(valid)):
        dt = (valid[i].timestamp - valid[i - 1].timestamp).total_seconds()
        if dt <= 0:
            continue
        if dt > expected_interval_s * 1.8:
            gap_count += 1
        p_prev = GeoPoint(lat=valid[i - 1].lat, lon=valid[i - 1].lon)
        p_curr = GeoPoint(lat=valid[i].lat, lon=valid[i].lon)
        dist = haversine_distance_m(p_prev, p_curr)
        speed = dist / dt
        speeds.append(speed)
        if dist < stop_displacement_m or speed < 0.35:
            stop_duration_s += dt

    if planned_route:
        deviations = [
            point_to_polyline_distance_m(
                GeoPoint(lat=o.lat, lon=o.lon), planned_route
            )
            for o in valid
        ]
        dev_mean = float(np.mean(deviations))
        dev_max = float(np.max(deviations))
    else:
        dev_mean = 0.0
        dev_max = 0.0

    speed_arr = np.array(speeds, dtype=np.float64) if speeds else np.array([0.0])
    total_steps = max(1, len(valid) - 1)

    return WindowFeatures(
        mean_speed_mps=float(np.mean(speed_arr)),
        max_speed_mps=float(np.max(speed_arr)),
        std_speed_mps=float(np.std(speed_arr)),
        stop_duration_s=float(stop_duration_s),
        route_deviation_mean_m=dev_mean,
        route_deviation_max_m=dev_max,
        missing_gap_ratio=float(gap_count / total_steps),
    )


def _calibrate_threshold_f1(
    scores: np.ndarray, y_true: np.ndarray, grid_size: int = 120
) -> float:
    """Select threshold tau maximizing F1-score on validation scores."""
    if len(scores) == 0 or np.all(y_true == 0):
        return float(np.percentile(scores, 95)) if len(scores) else 0.5
    lo, hi = float(np.min(scores)), float(np.max(scores))
    if math_is_close(lo, hi):
        return lo
    best_tau = lo
    best_f1 = -1.0
    for tau in np.linspace(lo, hi, grid_size):
        preds = (scores >= tau).astype(int)
        tp = int(np.sum((preds == 1) & (y_true == 1)))
        fp = int(np.sum((preds == 1) & (y_true == 0)))
        fn = int(np.sum((preds == 0) & (y_true == 1)))
        denom = 2 * tp + fp + fn
        f1 = (2 * tp / denom) if denom > 0 else 0.0
        if f1 > best_f1:
            best_f1 = f1
            best_tau = float(tau)
    return best_tau


def math_is_close(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol


class RuleBasedDetector:
    """Transparent rule-based movement anomaly baseline."""

    name = "Rule-Based"

    def __init__(
        self,
        max_stop_s: float = 65.0,
        min_dev_with_stop_m: float = 35.0,
        max_route_dev_m: float = 95.0,
        max_speed_mps: float = 4.8,
        max_gap_ratio: float = 0.5,
    ) -> None:
        self.max_stop_s = max_stop_s
        self.min_dev_with_stop_m = min_dev_with_stop_m
        self.max_route_dev_m = max_route_dev_m
        self.max_speed_mps = max_speed_mps
        self.max_gap_ratio = max_gap_ratio
        self.threshold = 1.0

    def fit(
        self,
        X_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
    ) -> "RuleBasedDetector":
        return self

    def score(self, X: np.ndarray) -> np.ndarray:
        # Columns: 0=mean_speed, 1=max_speed, 2=std_speed, 3=stop_s, 4=dev_mean, 5=dev_max, 6=gap_ratio
        stop_off_route = np.minimum(
            X[:, 3] / self.max_stop_s,
            X[:, 4] / self.min_dev_with_stop_m,
        )
        route_dev_ratio = X[:, 5] / self.max_route_dev_m
        speed_ratio = X[:, 1] / self.max_speed_mps
        gap_ratio = X[:, 6] / self.max_gap_ratio
        return np.maximum.reduce([stop_off_route, route_dev_ratio, speed_ratio, gap_ratio])

    def predict(self, X: np.ndarray) -> np.ndarray:
        return (self.score(X) >= self.threshold).astype(int)


class LOFDetector:
    """Local Outlier Factor baseline trained on normal movement windows."""

    name = "Local Outlier Factor (LOF)"

    def __init__(self, n_neighbors: int = 20, contamination: float = 0.08) -> None:
        self.scaler = StandardScaler()
        self.model = LocalOutlierFactor(
            n_neighbors=n_neighbors,
            contamination=contamination,
            novelty=True,
        )
        self.threshold: float = 1.5

    def fit(
        self,
        X_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
    ) -> "LOFDetector":
        X_scaled = self.scaler.fit_transform(X_train)
        self.model.fit(X_scaled)
        if X_val is not None and y_val is not None:
            val_scores = self.score(X_val)
            self.threshold = _calibrate_threshold_f1(val_scores, y_val)
        else:
            train_scores = self.score(X_train)
            self.threshold = float(np.percentile(train_scores, 95))
        return self

    def score(self, X: np.ndarray) -> np.ndarray:
        X_scaled = self.scaler.transform(X)
        return -self.model.score_samples(X_scaled)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return (self.score(X) >= self.threshold).astype(int)


class IsolationForestDetector:
    """Isolation Forest detector following paper Eq. 5: a(x) = -score_samples(x)."""

    name = "Isolation Forest"

    def __init__(
        self,
        n_estimators: int = 200,
        contamination: float = 0.08,
        random_state: int = 42,
    ) -> None:
        self.scaler = StandardScaler()
        self.model = IsolationForest(
            n_estimators=n_estimators,
            contamination=contamination,
            random_state=random_state,
        )
        self.threshold: float = 0.55

    def fit(
        self,
        X_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
    ) -> "IsolationForestDetector":
        X_scaled = self.scaler.fit_transform(X_train)
        self.model.fit(X_scaled)
        if X_val is not None and y_val is not None:
            val_scores = self.score(X_val)
            self.threshold = _calibrate_threshold_f1(val_scores, y_val)
        else:
            train_scores = self.score(X_train)
            self.threshold = float(np.percentile(train_scores, 95))
        return self

    def score(self, X: np.ndarray) -> np.ndarray:
        X_scaled = self.scaler.transform(X)
        return -self.model.score_samples(X_scaled)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return (self.score(X) >= self.threshold).astype(int)


class HybridGeofenceIFDetector:
    """Context-aware Geo-fencing + Isolation Forest fusion detector.

    Combines Isolation Forest anomaly scores with geographical zone context:
    - Restricted zone entry triggers immediate high risk.
    - Caution zone / restricted buffer lowers the anomaly threshold (higher sensitivity).
    - Safe zone attenuates mild stops (sightseeing/waiting) to reduce false positives.
    """

    name = "Geo-fencing + Isolation Forest"

    def __init__(
        self,
        n_estimators: int = 200,
        contamination: float = 0.08,
        random_state: int = 42,
        safe_margin: float = 0.04,
        caution_boost: float = 0.06,
    ) -> None:
        self.iforest = IsolationForestDetector(
            n_estimators=n_estimators,
            contamination=contamination,
            random_state=random_state,
        )
        self.safe_margin = safe_margin
        self.caution_boost = caution_boost

    @property
    def threshold(self) -> float:
        return self.iforest.threshold

    def fit(
        self,
        X_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        zone_ctx_val: Optional[list[tuple[Optional[ZoneCategory], ZoneState]]] = None,
    ) -> "HybridGeofenceIFDetector":
        self.iforest.fit(X_train, X_val=X_val, y_val=y_val)
        if X_val is not None and y_val is not None and zone_ctx_val is not None:
            val_scores = self.score(X_val, zone_ctx_val)
            self.iforest.threshold = _calibrate_threshold_f1(val_scores, y_val)
        return self

    def score(
        self,
        X: np.ndarray,
        zone_contexts: Optional[list[tuple[Optional[ZoneCategory], ZoneState]]] = None,
    ) -> np.ndarray:
        base_scores = self.iforest.score(X)
        if zone_contexts is None:
            return base_scores

        adjusted = base_scores.copy()
        for i, (cat, state) in enumerate(zone_contexts):
            if cat == ZoneCategory.RESTRICTED and state == ZoneState.INSIDE:
                adjusted[i] = max(adjusted[i], self.iforest.threshold + 0.35)
            elif (
                cat == ZoneCategory.RESTRICTED and state == ZoneState.WARNING_BUFFER
            ) or (cat == ZoneCategory.CAUTION and state == ZoneState.INSIDE):
                adjusted[i] += self.caution_boost
            elif cat == ZoneCategory.SAFE and state == ZoneState.INSIDE:
                # Sightseeing/waiting in safe zone: dampen mild stop-only spikes
                adjusted[i] -= self.safe_margin
        return adjusted

    def predict(
        self,
        X: np.ndarray,
        zone_contexts: Optional[list[tuple[Optional[ZoneCategory], ZoneState]]] = None,
    ) -> np.ndarray:
        return (self.score(X, zone_contexts) >= self.iforest.threshold).astype(int)
