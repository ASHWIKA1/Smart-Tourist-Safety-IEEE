export type IncidentStatus = "pending" | "acknowledged" | "in_progress" | "resolved";
export type AlertPriority = "info" | "warning" | "high" | "critical";
export type ZoneCategory = "safe" | "caution" | "restricted";

export interface GeoPoint {
  lat: number;
  lon: number;
}

export interface GeoZone {
  zone_id: string;
  name: string;
  category: ZoneCategory;
  center?: GeoPoint | null;
  radius_m?: number | null;
  buffer_m: number;
  polygon?: GeoPoint[] | null;
}

export interface Incident {
  alert_id: string;
  tourist_id: string;
  event_timestamp: string;
  lat: number;
  lon: number;
  priority: AlertPriority;
  reason: string;
  zone_id?: string | null;
  zone_category?: string | null;
  anomaly_score?: number | null;
  status: IncidentStatus;
  created_at: string;
  acknowledged_at?: string | null;
  in_progress_at?: string | null;
  resolved_at?: string | null;
}

export interface VerificationResult {
  valid: boolean;
  reason: string;
  did: string;
  credential_id: string;
  hash_match: boolean;
  signature_valid: boolean;
  issuer_trusted: boolean;
  not_expired: boolean;
  not_revoked: boolean;
  not_replayed: boolean;
  latency_ms: number;
}

export interface LedgerResponse {
  chain_intact: boolean;
  block_count: number;
  blocks: Array<{
    index: number;
    timestamp: string;
    tx_type: string;
    payload: Record<string, unknown>;
    prev_hash: string;
    block_hash: string;
  }>;
}
