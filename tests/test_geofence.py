"""Unit tests for geo-fencing and spatial risk classification."""

from datetime import datetime, timedelta, timezone

from tourist_safety.geofence import (
    GeoFenceEngine,
    evaluate_zone,
    haversine_distance_m,
    point_in_polygon,
)
from tourist_safety.models import (
    GeoPoint,
    GeoZone,
    GPSObservation,
    ZoneCategory,
    ZoneState,
)


def test_haversine_zero_and_known_distance():
    p1 = GeoPoint(lat=11.3610, lon=77.8280)
    assert haversine_distance_m(p1, p1) == 0.0

    # ~111.19 km per degree of latitude
    p2 = GeoPoint(lat=12.3610, lon=77.8280)
    dist = haversine_distance_m(p1, p2)
    assert 110_500 < dist < 111_500


def test_circular_zone_inside_buffer_outside():
    center = GeoPoint(lat=11.3610, lon=77.8280)
    zone = GeoZone(
        zone_id="z1",
        name="Cliff",
        category=ZoneCategory.RESTRICTED,
        center=center,
        radius_m=100.0,
        buffer_m=30.0,
    )
    inside = evaluate_zone(center, zone)
    assert inside.state == ZoneState.INSIDE
    assert inside.action == "restricted_alert"

    # ~111 m north -> inside warning buffer (100 < d <= 130)
    buffer_pt = GeoPoint(lat=11.3610 + 0.001, lon=77.8280)
    buf_res = evaluate_zone(buffer_pt, zone)
    assert buf_res.state == ZoneState.WARNING_BUFFER
    assert buf_res.action == "restricted_boundary_warning"

    # ~222 m north -> outside
    out_pt = GeoPoint(lat=11.3610 + 0.002, lon=77.8280)
    out_res = evaluate_zone(out_pt, zone)
    assert out_res.state == ZoneState.OUTSIDE
    assert out_res.action == "none"


def test_polygon_zone_and_entry_exit_transitions():
    square = [
        GeoPoint(lat=11.3600, lon=77.8270),
        GeoPoint(lat=11.3600, lon=77.8290),
        GeoPoint(lat=11.3620, lon=77.8290),
        GeoPoint(lat=11.3620, lon=77.8270),
    ]
    assert point_in_polygon(GeoPoint(lat=11.3610, lon=77.8280), square) is True
    assert point_in_polygon(GeoPoint(lat=11.3650, lon=77.8280), square) is False

    zone = GeoZone(
        zone_id="poly-1",
        name="Restricted Ruins",
        category=ZoneCategory.RESTRICTED,
        polygon=square,
        buffer_m=20.0,
    )
    engine = GeoFenceEngine([zone])
    t0 = datetime(2026, 11, 12, 10, 0, 0, tzinfo=timezone.utc)

    _, t1 = engine.evaluate_observation(
        GPSObservation(tourist_id="t1", timestamp=t0, lat=11.3650, lon=77.8280)
    )
    assert t1 == []  # started outside

    _, t2 = engine.evaluate_observation(
        GPSObservation(
            tourist_id="t1",
            timestamp=t0 + timedelta(seconds=10),
            lat=11.3610,
            lon=77.8280,
        )
    )
    assert len(t2) == 1
    assert t2[0].event_type == "enter_zone"

    _, t3 = engine.evaluate_observation(
        GPSObservation(
            tourist_id="t1",
            timestamp=t0 + timedelta(seconds=20),
            lat=11.3650,
            lon=77.8280,
        )
    )
    assert len(t3) == 1
    assert t3[0].event_type == "exit_zone"
