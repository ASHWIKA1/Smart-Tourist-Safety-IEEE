import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { GeoZone, Incident } from "../types";

interface SafetyMapProps {
  zones: GeoZone[];
  incidents: Incident[];
  selectedIncidentId: string | null;
  onSelectIncident: (alertId: string) => void;
}

const ZONE_COLORS: Record<string, string> = {
  safe: "#16a34a",
  caution: "#d97706",
  restricted: "#dc2626",
};

const PRIORITY_COLORS: Record<string, string> = {
  critical: "#991b1b",
  high: "#dc2626",
  warning: "#d97706",
  info: "#2563eb",
};

export function SafetyMap({
  zones,
  incidents,
  selectedIncidentId,
  onSelectIncident,
}: SafetyMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const zonesLayerRef = useRef<L.LayerGroup | null>(null);
  const incidentsLayerRef = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current, {
      center: [11.3625, 77.8325],
      zoom: 15,
    });

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
      maxZoom: 19,
    }).addTo(map);

    zonesLayerRef.current = L.layerGroup().addTo(map);
    incidentsLayerRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const layer = zonesLayerRef.current;
    if (!layer) return;
    layer.clearLayers();

    for (const z of zones) {
      const color = ZONE_COLORS[z.category] ?? "#64748b";
      if (z.center && z.radius_m) {
        L.circle([z.center.lat, z.center.lon], {
          radius: z.radius_m,
          color,
          fillColor: color,
          fillOpacity: 0.18,
          weight: 2,
        })
          .bindPopup(`<strong>${z.name}</strong><br/>Category: ${z.category}<br/>Radius: ${z.radius_m} m`)
          .addTo(layer);

        if (z.buffer_m > 0) {
          L.circle([z.center.lat, z.center.lon], {
            radius: z.radius_m + z.buffer_m,
            color,
            dashArray: "5 6",
            fillOpacity: 0.03,
            weight: 1.5,
          }).addTo(layer);
        }
      } else if (z.polygon && z.polygon.length >= 3) {
        L.polygon(
          z.polygon.map((p) => [p.lat, p.lon] as [number, number]),
          {
            color,
            fillColor: color,
            fillOpacity: 0.18,
            weight: 2,
          }
        )
          .bindPopup(`<strong>${z.name}</strong><br/>Category: ${z.category}`)
          .addTo(layer);
      }
    }
  }, [zones]);

  useEffect(() => {
    const layer = incidentsLayerRef.current;
    const map = mapRef.current;
    if (!layer || !map) return;
    layer.clearLayers();

    for (const inc of incidents) {
      const color = PRIORITY_COLORS[inc.priority] ?? "#2563eb";
      const isSelected = inc.alert_id === selectedIncidentId;

      const marker = L.circleMarker([inc.lat, inc.lon], {
        radius: isSelected ? 11 : 8,
        color: isSelected ? "#0f172a" : "#ffffff",
        weight: isSelected ? 3 : 2,
        fillColor: color,
        fillOpacity: inc.status === "resolved" ? 0.45 : 0.92,
      });

      marker.bindPopup(
        `<div>
          <strong>${inc.priority.toUpperCase()}</strong> (${inc.status})<br/>
          Reason: ${inc.reason}<br/>
          Tourist: ${inc.tourist_id}<br/>
          Time: ${new Date(inc.event_timestamp).toLocaleString()}
        </div>`
      );
      marker.on("click", () => onSelectIncident(inc.alert_id));
      marker.addTo(layer);

      if (isSelected) {
        map.panTo([inc.lat, inc.lon], { animate: true });
      }
    }
  }, [incidents, selectedIncidentId, onSelectIncident]);

  return (
    <div
      ref={containerRef}
      className="map-canvas"
      aria-label="OpenStreetMap tourist safety monitoring view"
    />
  );
}
