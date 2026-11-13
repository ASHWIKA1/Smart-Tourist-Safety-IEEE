"""Geo-fencing and spatial risk classification engine.

Implements Haversine great-circle distance (paper Eq. 2-3), circular and
polygonal zone evaluation with warning buffers (Algorithm 2), and stateful
entry/exit event tracking.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .models import (
    GeoPoint,
    GeoZone,
    GPSObservation,
    ZoneCategory,
    ZoneEvaluationResult,
    ZoneState,
)

EARTH_RADIUS_M = 6_371_000.0


def haversine_distance_m(p1: GeoPoint, p2: GeoPoint) -> float:
    """Compute great-circle distance in metres between two WGS84 points."""
    phi1 = math.radians(p1.lat)
    phi2 = math.radians(p2.lat)
    dphi = math.radians(p2.lat - p1.lat)
    dlambda = math.radians(p2.lon - p1.lon)

    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(dlambda / 2.0) ** 2)
    )
    a = min(1.0, max(0.0, a))
    return 2.0 * EARTH_RADIUS_M * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def _to_local_xy_m(origin: GeoPoint, point: GeoPoint) -> tuple[float, float]:
    """Project point into local tangent plane (metres) relative to origin."""
    lat0 = math.radians(origin.lat)
    x = EARTH_RADIUS_M * math.radians(point.lon - origin.lon) * math.cos(lat0)
    y = EARTH_RADIUS_M * math.radians(point.lat - origin.lat)
    return x, y


def point_to_segment_distance_m(p: GeoPoint, a: GeoPoint, b: GeoPoint) -> float:
    """Minimum distance in metres from point p to line segment [a, b]."""
    ax, ay = _to_local_xy_m(p, a)
    bx, by = _to_local_xy_m(p, b)
    dx = bx - ax
    dy = by - ay
    len_sq = dx * dx + dy * dy
    if len_sq == 0.0:
        return math.hypot(ax, ay)
    t = max(0.0, min(1.0, -(ax * dx + ay * dy) / len_sq))
    proj_x = ax + t * dx
    proj_y = ay + t * dy
    return math.hypot(proj_x, proj_y)


def point_to_polyline_distance_m(p: GeoPoint, polyline: list[GeoPoint]) -> float:
    """Minimum distance in metres from point p to any segment in polyline."""
    if not polyline:
        return 0.0
    if len(polyline) == 1:
        return haversine_distance_m(p, polyline[0])
    return min(
        point_to_segment_distance_m(p, polyline[i], polyline[i + 1])
        for i in range(len(polyline) - 1)
    )


def point_in_polygon(p: GeoPoint, polygon: list[GeoPoint]) -> bool:
    """Ray-casting point-in-polygon test."""
    if len(polygon) < 3:
        return False
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i].lon, polygon[i].lat
        xj, yj = polygon[j].lon, polygon[j].lat
        intersects = ((yi > p.lat) != (yj > p.lat)) and (
            p.lon < (xj - xi) * (p.lat - yi) / ((yj - yi) or 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def _zone_action(category: ZoneCategory, state: ZoneState) -> str:
    if state == ZoneState.OUTSIDE:
        return "none"
    if category == ZoneCategory.SAFE:
        return "normal_monitoring"
    if category == ZoneCategory.CAUTION:
        return "caution_advisory" if state == ZoneState.INSIDE else "approaching_caution"
    # RESTRICTED
    return (
        "restricted_alert"
        if state == ZoneState.INSIDE
        else "restricted_boundary_warning"
    )


def evaluate_zone(point: GeoPoint, zone: GeoZone) -> ZoneEvaluationResult:
    """Evaluate a GPS point against a circular or polygonal GeoZone."""
    if zone.center is not None and zone.radius_m is not None:
        dist = haversine_distance_m(point, zone.center)
        if dist <= zone.radius_m:
            state = ZoneState.INSIDE
        elif dist <= zone.radius_m + zone.buffer_m:
            state = ZoneState.WARNING_BUFFER
        else:
            state = ZoneState.OUTSIDE
        boundary_dist = max(0.0, dist - zone.radius_m)
    elif zone.polygon is not None and len(zone.polygon) >= 3:
        closed_edges = zone.polygon + [zone.polygon[0]]
        edge_dist = point_to_polyline_distance_m(point, closed_edges)
        if point_in_polygon(point, zone.polygon):
            state = ZoneState.INSIDE
            boundary_dist = 0.0
        elif edge_dist <= zone.buffer_m:
            state = ZoneState.WARNING_BUFFER
            boundary_dist = edge_dist
        else:
            state = ZoneState.OUTSIDE
            boundary_dist = edge_dist
    else:
        raise ValueError(f"Zone {zone.zone_id} must define center+radius_m or polygon.")

    return ZoneEvaluationResult(
        zone_id=zone.zone_id,
        zone_name=zone.name,
        category=zone.category,
        state=state,
        distance_m=round(boundary_dist, 3),
        action=_zone_action(zone.category, state),
    )


@dataclass
class ZoneTransitionEvent:
    tourist_id: str
    zone_id: str
    category: ZoneCategory
    previous_state: ZoneState
    new_state: ZoneState
    timestamp: datetime
    event_type: str  # enter_zone, exit_zone, enter_buffer, exit_buffer


class GeoFenceEngine:
    """Manages configured zones and tracks entry/exit transitions per tourist."""

    def __init__(
        self,
        zones: Optional[list[GeoZone]] = None,
        max_gps_accuracy_m: float = 50.0,
    ) -> None:
        self._zones: dict[str, GeoZone] = {z.zone_id: z for z in (zones or [])}
        self._max_gps_accuracy_m = max_gps_accuracy_m
        self._last_states: dict[tuple[str, str], ZoneState] = {}
        self.transition_history: list[ZoneTransitionEvent] = []

    def add_zone(self, zone: GeoZone) -> None:
        self._zones[zone.zone_id] = zone

    def list_zones(self) -> list[GeoZone]:
        return list(self._zones.values())

    def evaluate_observation(
        self, obs: GPSObservation
    ) -> tuple[list[ZoneEvaluationResult], list[ZoneTransitionEvent]]:
        """Evaluate all zones for a GPSObservation and record state transitions."""
        if obs.accuracy_m > self._max_gps_accuracy_m:
            return [], []

        pt = GeoPoint(lat=obs.lat, lon=obs.lon)
        results: list[ZoneEvaluationResult] = []
        transitions: list[ZoneTransitionEvent] = []

        for zone in self._zones.values():
            res = evaluate_zone(pt, zone)
            results.append(res)

            key = (obs.tourist_id, zone.zone_id)
            prev = self._last_states.get(key, ZoneState.OUTSIDE)
            if res.state != prev:
                event_type = self._classify_transition(prev, res.state)
                evt = ZoneTransitionEvent(
                    tourist_id=obs.tourist_id,
                    zone_id=zone.zone_id,
                    category=zone.category,
                    previous_state=prev,
                    new_state=res.state,
                    timestamp=obs.timestamp,
                    event_type=event_type,
                )
                transitions.append(evt)
                self.transition_history.append(evt)
                self._last_states[key] = res.state

        return results, transitions

    @staticmethod
    def _classify_transition(prev: ZoneState, curr: ZoneState) -> str:
        if curr == ZoneState.INSIDE:
            return "enter_zone"
        if prev == ZoneState.INSIDE and curr != ZoneState.INSIDE:
            return "exit_zone"
        if curr == ZoneState.WARNING_BUFFER:
            return "enter_buffer"
        return "exit_buffer"

    @staticmethod
    def highest_risk_zone(
        results: list[ZoneEvaluationResult],
    ) -> Optional[ZoneEvaluationResult]:
        """Return the most severe active zone result (restricted > caution > safe)."""
        active = [r for r in results if r.state != ZoneState.OUTSIDE]
        if not active:
            return None
        priority = {
            (ZoneCategory.RESTRICTED, ZoneState.INSIDE): 6,
            (ZoneCategory.RESTRICTED, ZoneState.WARNING_BUFFER): 5,
            (ZoneCategory.CAUTION, ZoneState.INSIDE): 4,
            (ZoneCategory.CAUTION, ZoneState.WARNING_BUFFER): 3,
            (ZoneCategory.SAFE, ZoneState.INSIDE): 2,
            (ZoneCategory.SAFE, ZoneState.WARNING_BUFFER): 1,
        }
        return max(active, key=lambda r: priority.get((r.category, r.state), 0))
