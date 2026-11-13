"""Integration tests for FastAPI backend, RBAC, credentials, telemetry, SOS, and WebSockets."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from tourist_safety.api.app import create_app


@pytest.fixture()
def client(tmp_path):
    db_file = tmp_path / "test_safety.db"
    app = create_app(database_url=f"sqlite:///{db_file}")
    with TestClient(app) as c:
        yield c


def _register_and_auth(client: TestClient, email: str, role: str, **extra):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret123", "role": role, **extra},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    return data["user_id"], headers


def test_health_and_rbac_enforcement(client: TestClient):
    h = client.get("/health")
    assert h.status_code == 200
    assert h.json()["zones_loaded"] >= 3
    assert h.json()["ledger_intact"] is True

    tourist_id, tourist_headers = _register_and_auth(
        client, "t1@example.com", "tourist", full_name="Tourist One"
    )
    _, auth_headers = _register_and_auth(client, "officer@example.com", "authority")

    # Tourist cannot issue credentials or list all incidents
    assert (
        client.post(
            "/api/v1/credentials/issue",
            json={"tourist_id": tourist_id},
            headers=tourist_headers,
        ).status_code
        == 403
    )
    assert client.get("/api/v1/incidents", headers=tourist_headers).status_code == 403

    # Authority can list zones and view tourist profile
    assert client.get(f"/api/v1/tourists/{tourist_id}", headers=auth_headers).status_code == 200
    assert len(client.get("/api/v1/zones", headers=auth_headers).json()) >= 3


def test_credential_issuance_verification_and_revocation_api(client: TestClient):
    tourist_id, tourist_headers = _register_and_auth(
        client,
        "ajay@example.com",
        "tourist",
        full_name="Ajay K",
        passport_or_id_number="P112233",
        emergency_contact_name="Geetha",
        emergency_contact_phone="+91-9000011111",
    )
    _, auth_headers = _register_and_auth(client, "verifier@example.com", "authority")

    issued = client.post(
        "/api/v1/credentials/issue",
        json={"tourist_id": tourist_id, "validity_days": 10},
        headers=auth_headers,
    )
    assert issued.status_code == 200, issued.text
    vc = issued.json()["credential"]

    # Tourist fetches own VC
    my_vc = client.get("/api/v1/credentials/me", headers=tourist_headers)
    assert my_vc.status_code == 200
    assert my_vc.json()["credential_id"] == vc["credential_id"]

    # Verify valid VC
    ver1 = client.post(
        "/api/v1/credentials/verify",
        json={"credential": vc, "presentation_nonce": "api-nonce-1"},
        headers=auth_headers,
    )
    assert ver1.status_code == 200
    assert ver1.json()["valid"] is True

    # Tampered VC rejected
    tampered = dict(vc)
    tampered["credential_subject"] = dict(vc["credential_subject"])
    tampered["credential_subject"]["passport_or_id_number"] = "FORGED999"
    ver_tampered = client.post(
        "/api/v1/credentials/verify",
        json={"credential": tampered, "presentation_nonce": "api-nonce-2"},
        headers=auth_headers,
    )
    assert ver_tampered.json()["valid"] is False
    assert ver_tampered.json()["hash_match"] is False

    # Revoke and verify rejected
    rev = client.post(
        f"/api/v1/credentials/{vc['credential_id']}/revoke",
        json={"reason": "trip_ended"},
        headers=auth_headers,
    )
    assert rev.status_code == 200
    ver_rev = client.post(
        "/api/v1/credentials/verify",
        json={"credential": vc, "presentation_nonce": "api-nonce-3"},
        headers=auth_headers,
    )
    assert ver_rev.json()["valid"] is False
    assert ver_rev.json()["not_revoked"] is False


def test_end_to_end_incident_workflow_and_websocket(client: TestClient):
    tourist_id, tourist_headers = _register_and_auth(
        client, "ashwika@example.com", "tourist", full_name="Ashwika K", tracking_consent=False
    )
    _, auth_headers = _register_and_auth(client, "control@example.com", "authority")

    # Tracking blocked before consent
    blocked = client.post(
        "/api/v1/telemetry/gps",
        json={"lat": 11.3610, "lon": 77.8280, "accuracy_m": 4.0},
        headers=tourist_headers,
    )
    assert blocked.status_code == 403

    # Enable consent
    consent = client.put(
        "/api/v1/tourists/me/consent",
        json={"tracking_consent": True},
        headers=tourist_headers,
    )
    assert consent.status_code == 200
    assert consent.json()["tracking_consent"] is True

    # Restricted cliff zone center from default_test_geography(): dx=680m, dy=470m from (11.3610, 77.8280)
    zones = client.get("/api/v1/zones", headers=auth_headers).json()
    restricted = next(z for z in zones if z["category"] == "restricted")
    r_lat = restricted["center"]["lat"]
    r_lon = restricted["center"]["lon"]

    # Connect authority WebSocket and ingest GPS point inside restricted zone
    with client.websocket_connect("/ws/authority/alerts") as ws:
        t0 = datetime.now(timezone.utc)
        resp = client.post(
            "/api/v1/telemetry/gps",
            json={
                "lat": r_lat,
                "lon": r_lon,
                "accuracy_m": 3.5,
                "timestamp": (t0 + timedelta(seconds=5)).isoformat(),
            },
            headers=tourist_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["incident"] is not None
        assert body["incident"]["priority"] == "high"
        assert "restricted_zone_entry" in body["incident"]["reason"]

        ws_msg = ws.receive_json()
        assert ws_msg["event"] == "incident_created"
        alert_id = ws_msg["incident"]["alert_id"]

    # Authority acknowledges and resolves incident
    ack = client.patch(
        f"/api/v1/incidents/{alert_id}/status",
        json={"status": "acknowledged"},
        headers=auth_headers,
    )
    assert ack.status_code == 200
    assert ack.json()["acknowledged_at"] is not None

    res = client.patch(
        f"/api/v1/incidents/{alert_id}/status",
        json={"status": "resolved"},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "resolved"
    assert res.json()["resolved_at"] is not None

    # Tourist triggers manual SOS
    sos = client.post(
        "/api/v1/sos",
        json={"lat": 11.3615, "lon": 77.8285, "note": "injured_on_trail"},
        headers=tourist_headers,
    )
    assert sos.status_code == 201
    assert sos.json()["priority"] == "critical"
