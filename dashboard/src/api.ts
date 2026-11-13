import type {
  GeoZone,
  Incident,
  IncidentStatus,
  LedgerResponse,
  VerificationResult,
  ZoneCategory,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function loginAuthority(email: string, password: string) {
  return request<{ access_token: string; user_id: string; role: string }>(
    "/api/v1/auth/login",
    {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }
  );
}

export async function registerAuthority(email: string, password: string) {
  return request<{ access_token: string; user_id: string; role: string }>(
    "/api/v1/auth/register",
    {
      method: "POST",
      body: JSON.stringify({ email, password, role: "authority" }),
    }
  );
}

export async function fetchZones(token: string) {
  return request<GeoZone[]>("/api/v1/zones", {}, token);
}

export async function createZone(
  token: string,
  payload: {
    name: string;
    category: ZoneCategory;
    center: { lat: number; lon: number };
    radius_m: number;
    buffer_m: number;
  }
) {
  return request<GeoZone>(
    "/api/v1/zones",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token
  );
}

export async function fetchIncidents(token: string, statusFilter?: string) {
  const query = statusFilter && statusFilter !== "all" ? `?status=${statusFilter}` : "";
  return request<Incident[]>(`/api/v1/incidents${query}`, {}, token);
}

export async function updateIncidentStatus(
  token: string,
  alertId: string,
  status: IncidentStatus
) {
  return request<Incident>(
    `/api/v1/incidents/${alertId}/status`,
    {
      method: "PATCH",
      body: JSON.stringify({ status }),
    },
    token
  );
}

export async function verifyCredential(
  token: string,
  credential: unknown,
  presentationNonce?: string
) {
  return request<VerificationResult>(
    "/api/v1/credentials/verify",
    {
      method: "POST",
      body: JSON.stringify({
        credential,
        presentation_nonce: presentationNonce || undefined,
      }),
    },
    token
  );
}

export async function revokeCredential(
  token: string,
  credentialId: string,
  reason: string
) {
  return request<{ credential_id: string; revoked: boolean }>(
    `/api/v1/credentials/${credentialId}/revoke`,
    {
      method: "POST",
      body: JSON.stringify({ reason }),
    },
    token
  );
}

export async function fetchLedgerBlocks(token: string) {
  return request<LedgerResponse>("/api/v1/ledger/blocks", {}, token);
}
