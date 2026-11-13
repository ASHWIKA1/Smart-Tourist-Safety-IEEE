import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createZone,
  fetchIncidents,
  fetchZones,
  loginAuthority,
  registerAuthority,
  updateIncidentStatus,
} from "./api";
import { CredentialPanel } from "./components/CredentialPanel";
import { SafetyMap } from "./components/SafetyMap";
import type { GeoZone, Incident, IncidentStatus, ZoneCategory } from "./types";

export function App() {
  const [token, setToken] = useState<string>(() => localStorage.getItem("auth_token") ?? "");
  const [email, setEmail] = useState("authority@safety.local");
  const [password, setPassword] = useState("Authority123!");
  const [authError, setAuthError] = useState<string | null>(null);

  const [zones, setZones] = useState<GeoZone[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState(false);

  // Zone creation form state
  const [zoneName, setZoneName] = useState("");
  const [zoneCategory, setZoneCategory] = useState<ZoneCategory>("caution");
  const [zoneLat, setZoneLat] = useState("11.3635");
  const [zoneLon, setZoneLon] = useState("77.8325");
  const [zoneRadius, setZoneRadius] = useState("100");

  const loadData = useCallback(async () => {
    if (!token) return;
    const [z, inc] = await Promise.all([
      fetchZones(token),
      fetchIncidents(token, statusFilter),
    ]);
    setZones(z);
    setIncidents(inc);
  }, [token, statusFilter]);

  useEffect(() => {
    loadData().catch(() => {
      // Token may have expired
      setToken("");
      localStorage.removeItem("auth_token");
    });
  }, [loadData]);

  useEffect(() => {
    if (!token) return;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/authority/alerts`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => setWsConnected(true);
    ws.onclose = () => setWsConnected(false);
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as {
          event: string;
          incident: Incident;
        };
        if (!msg.incident) return;
        setIncidents((prev) => {
          const without = prev.filter((i) => i.alert_id !== msg.incident.alert_id);
          return [msg.incident, ...without];
        });
      } catch {
        // Ignore malformed WS message
      }
    };

    return () => ws.close();
  }, [token]);

  async function handleAuth(mode: "login" | "register") {
    setAuthError(null);
    try {
      const res =
        mode === "login"
          ? await loginAuthority(email, password)
          : await registerAuthority(email, password);
      localStorage.setItem("auth_token", res.access_token);
      setToken(res.access_token);
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "Authentication failed");
    }
  }

  async function handleStatusChange(alertId: string, nextStatus: IncidentStatus) {
    if (!token) return;
    const updated = await updateIncidentStatus(token, alertId, nextStatus);
    setIncidents((prev) =>
      prev.map((item) => (item.alert_id === updated.alert_id ? updated : item))
    );
  }

  async function handleCreateZone(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    const created = await createZone(token, {
      name: zoneName,
      category: zoneCategory,
      center: { lat: Number(zoneLat), lon: Number(zoneLon) },
      radius_m: Number(zoneRadius),
      buffer_m: 25,
    });
    setZones((prev) => [...prev, created]);
    setZoneName("");
  }

  const stats = useMemo(() => {
    return {
      total: incidents.length,
      pending: incidents.filter((i) => i.status === "pending").length,
      restricted: incidents.filter((i) => i.reason.includes("restricted")).length,
      anomalies: incidents.filter((i) => i.reason.includes("anomaly")).length,
      sos: incidents.filter((i) => i.priority === "critical").length,
    };
  }, [incidents]);

  if (!token) {
    return (
      <main className="auth-shell">
        <div className="auth-card">
          <h1>Smart Tourist Safety — Authority Control</h1>
          <p className="muted">
            Sign in with an authority account to monitor live tourist alerts,
            geo-fences, AI anomalies, and verifiable credentials.
          </p>
          {authError && <p className="alert-error">{authError}</p>}
          <label htmlFor="auth-email">Authority Email</label>
          <input
            id="auth-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <label htmlFor="auth-pass">Password</label>
          <input
            id="auth-pass"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <div className="row-actions">
            <button
              type="button"
              className="btn-primary"
              onClick={() => handleAuth("login")}
            >
              Sign In
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => handleAuth("register")}
            >
              Register Authority Account
            </button>
          </div>
        </div>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <h1>Authority Monitoring Dashboard</h1>
          <span className={`ws-pill ${wsConnected ? "online" : "offline"}`}>
            {wsConnected ? "Live WebSocket Connected" : "WebSocket Disconnected"}
          </span>
        </div>
        <div className="row-actions">
          <button type="button" className="btn-secondary" onClick={() => loadData()}>
            Refresh
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => {
              localStorage.removeItem("auth_token");
              setToken("");
            }}
          >
            Sign Out
          </button>
        </div>
      </header>

      <section className="kpi-grid">
        <div className="kpi-card"><span>Total Alerts</span><strong>{stats.total}</strong></div>
        <div className="kpi-card"><span>Pending</span><strong>{stats.pending}</strong></div>
        <div className="kpi-card"><span>Restricted Violations</span><strong>{stats.restricted}</strong></div>
        <div className="kpi-card"><span>AI Anomalies</span><strong>{stats.anomalies}</strong></div>
        <div className="kpi-card critical"><span>Manual SOS</span><strong>{stats.sos}</strong></div>
      </section>

      <div className="main-grid">
        <section className="panel">
          <div className="panel-header">
            <h2>Live Geo-Fence & Incident Map (OpenStreetMap)</h2>
            <span className="muted">{zones.length} active zones</span>
          </div>
          <SafetyMap
            zones={zones}
            incidents={incidents}
            selectedIncidentId={selectedIncidentId}
            onSelectIncident={setSelectedIncidentId}
          />
          <form onSubmit={handleCreateZone} className="zone-form">
            <input
              type="text"
              placeholder="New zone name"
              value={zoneName}
              onChange={(e) => setZoneName(e.target.value)}
              required
            />
            <select
              value={zoneCategory}
              onChange={(e) => setZoneCategory(e.target.value as ZoneCategory)}
            >
              <option value="safe">Safe</option>
              <option value="caution">Caution</option>
              <option value="restricted">Restricted</option>
            </select>
            <input
              type="number"
              step="0.0001"
              value={zoneLat}
              onChange={(e) => setZoneLat(e.target.value)}
              aria-label="Zone Latitude"
            />
            <input
              type="number"
              step="0.0001"
              value={zoneLon}
              onChange={(e) => setZoneLon(e.target.value)}
              aria-label="Zone Longitude"
            />
            <input
              type="number"
              min="10"
              value={zoneRadius}
              onChange={(e) => setZoneRadius(e.target.value)}
              aria-label="Radius in metres"
            />
            <button type="submit" className="btn-primary">Add Zone</button>
          </form>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Active Alerts & Incident History</h2>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              aria-label="Filter incidents by status"
            >
              <option value="all">All statuses</option>
              <option value="pending">Pending</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="in_progress">In Progress</option>
              <option value="resolved">Resolved</option>
            </select>
          </div>

          <div className="incident-list">
            {incidents.length === 0 && (
              <p className="muted">No incidents recorded for the selected filter.</p>
            )}
            {incidents.map((inc) => (
              <article
                key={inc.alert_id}
                className={`incident-card ${inc.priority} ${
                  selectedIncidentId === inc.alert_id ? "selected" : ""
                }`}
                onClick={() => setSelectedIncidentId(inc.alert_id)}
              >
                <div className="incident-top">
                  <span className={`badge ${inc.priority}`}>{inc.priority.toUpperCase()}</span>
                  <span className="status-tag">{inc.status}</span>
                </div>
                <div className="incident-reason">{inc.reason}</div>
                <div className="incident-meta">
                  Tourist: <code>{inc.tourist_id}</code> | Coords: {inc.lat.toFixed(5)},{" "}
                  {inc.lon.toFixed(5)}
                  {inc.anomaly_score !== null && inc.anomaly_score !== undefined
                    ? ` | AI Score: ${inc.anomaly_score}`
                    : ""}
                </div>
                <div className="incident-meta">
                  Event: {new Date(inc.event_timestamp).toLocaleString()}
                </div>
                <div className="row-actions" onClick={(e) => e.stopPropagation()}>
                  {inc.status === "pending" && (
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => handleStatusChange(inc.alert_id, "acknowledged")}
                    >
                      Acknowledge
                    </button>
                  )}
                  {(inc.status === "pending" || inc.status === "acknowledged") && (
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => handleStatusChange(inc.alert_id, "in_progress")}
                    >
                      In Progress
                    </button>
                  )}
                  {inc.status !== "resolved" && (
                    <button
                      type="button"
                      className="btn-primary"
                      onClick={() => handleStatusChange(inc.alert_id, "resolved")}
                    >
                      Resolve
                    </button>
                  )}
                </div>
              </article>
            ))}
          </div>
        </section>
      </div>

      <CredentialPanel token={token} />
    </div>
  );
}
